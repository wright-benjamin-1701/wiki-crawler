"""Typer CLI entry point for the wiki-dumps tool."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from wiki_dumps.settings import Settings

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="wiki",
    help="Download and process Wikipedia XML dumps.",
    no_args_is_help=True,
)

dump_app = typer.Typer(help="Manage Wikipedia dump files.", no_args_is_help=True)
extract_app = typer.Typer(help="Run extraction jobs.", no_args_is_help=True)

app.add_typer(dump_app, name="dump")
app.add_typer(extract_app, name="extract")

console = Console()

# --lang flag: when omitted, falls back to the WIKI_LANG setting (default "en").
_LANG_OPTION = "Wikipedia language code (default: WIKI_LANG, or 'en')"


def _resolve_lang(flag_lang: str | None) -> str:
    from wiki_dumps.settings import get_settings

    return flag_lang if flag_lang else get_settings().lang


# ---------------------------------------------------------------------------
# dump subcommands
# ---------------------------------------------------------------------------


@dump_app.command("list")
def dump_list(
    lang: Annotated[str | None, typer.Option("--lang", help=_LANG_OPTION)] = None,
) -> None:
    """List available dump dates on dumps.wikimedia.org."""
    from wiki_dumps.dumps.downloader import list_available_dumps

    lang = _resolve_lang(lang)
    all_dates = asyncio.run(list_available_dumps(lang, completed_only=False))
    completed = set(asyncio.run(list_available_dumps(lang, completed_only=True)))
    table = Table(title=f"Available {lang}wiki dumps (most recent 20)", show_header=True)
    table.add_column("Date")
    table.add_column("Status")
    for d in reversed(all_dates[-20:]):
        status = "[green]complete[/green]" if d in completed else "[yellow]in progress[/yellow]"
        table.add_row(d, status)
    console.print(table)


@dump_app.command("download")
def dump_download(
    lang: Annotated[str | None, typer.Option("--lang", help=_LANG_OPTION)] = None,
    date: Annotated[str, typer.Option("--date")] = "latest",
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Download the multistream dump for a language and date."""
    from wiki_dumps.dumps.downloader import download_dump, make_dump_file
    from wiki_dumps.settings import get_settings

    settings = get_settings()
    lang = _resolve_lang(lang)
    if date == "latest":
        from wiki_dumps.dumps.downloader import list_available_dumps

        dates = asyncio.run(list_available_dumps(lang, completed_only=True))
        if not dates:
            console.print("[red]No completed dumps found. Try again later or specify --date YYYYMMDD.[/red]")
            raise typer.Exit(1)
        date = dates[-1]
        console.print(f"[dim]Latest completed dump: {date}[/dim]")

    dump = make_dump_file(lang, date, settings.dump_dir)
    if dump.is_downloaded and not force:
        console.print("[yellow]Dump already downloaded. Use --force to re-download.[/yellow]")
        return
    asyncio.run(download_dump(dump, force=force))
    console.print(f"[green]Downloaded {lang}wiki-{date} to {settings.dump_dir}[/green]")


@dump_app.command("preprocess")
def dump_preprocess(
    dump: Annotated[Path | None, typer.Option("--dump", help="Path to dump file (auto-detected if omitted)")] = None,
    concurrent: Annotated[int, typer.Option("--concurrent", help="Parallel decompression threads.")] = 8,
) -> None:
    """Decompress all bz2 blocks to a flat raw file for fast subsequent extraction.

    Writes <dump>.xml.raw (~90 GB) and <dump>.xml.raw.idx alongside the original dump.
    After preprocessing, 'extract run' automatically uses the raw file (no bz2 overhead).
    """
    from wiki_dumps.dumps.paths import find_dump, index_path_for
    from wiki_dumps.dumps.preprocess import is_preprocessed, preprocess_dump
    from wiki_dumps.settings import get_settings

    settings = get_settings()

    if dump is None:
        dump = find_dump(settings.dump_dir)
        if dump is None:
            console.print(f"[red]No dump files found in {settings.dump_dir}.[/red]")
            raise typer.Exit(1)
        console.print(f"[dim]Using dump: {dump}[/dim]")

    if is_preprocessed(dump):
        console.print("[yellow]Raw file already exists. Delete it first to re-preprocess.[/yellow]")
        raise typer.Exit(0)

    index_path = index_path_for(dump)
    if not index_path.exists():
        console.print(f"[red]Index file not found: {index_path}[/red]")
        raise typer.Exit(1)

    preprocess_dump(dump, index_path, concurrent=concurrent)


@dump_app.command("info")
def dump_info(
    dump_path: Annotated[Path, typer.Argument(help="Path to the .xml.bz2 dump file")],
) -> None:
    """Show information about a downloaded dump file."""
    from wiki_dumps.dumps.paths import index_path_for

    if not dump_path.exists():
        console.print(f"[red]File not found: {dump_path}[/red]")
        raise typer.Exit(1)

    size_mb = dump_path.stat().st_size / (1024 * 1024)
    console.print(f"[bold]Dump:[/bold] {dump_path.name}")
    console.print(f"[bold]Size:[/bold] {size_mb:.1f} MB")
    index_path = index_path_for(dump_path)
    if index_path.exists():
        from wiki_dumps.dumps.index import parse_index

        blocks = parse_index(index_path)
        total_pages = sum(len(b.entries) for b in blocks)
        console.print(f"[bold]Blocks:[/bold] {len(blocks):,}")
        console.print(f"[bold]Pages in index:[/bold] {total_pages:,}")
    else:
        console.print("[yellow]Index file not found alongside dump.[/yellow]")


# ---------------------------------------------------------------------------
# extract subcommands
# ---------------------------------------------------------------------------


@extract_app.command("list")
def extract_list() -> None:
    """List all auto-discovered extraction jobs."""
    from wiki_dumps.jobs import discover_job_classes

    classes = discover_job_classes()
    table = Table(title="Registered extraction jobs")
    table.add_column("Name")
    table.add_column("Class")
    table.add_column("Default DB")
    table.add_column("Description")
    for job_name, cls in sorted(classes.items()):
        doc = (cls.__doc__ or "").strip().splitlines()
        description = doc[0] if doc else ""
        table.add_row(job_name, cls.__name__, getattr(cls, "default_db_url", "—"), description)
    console.print(table)


def _resolve_concurrent(flag_value: int | None, settings: Settings) -> tuple[int, bool]:
    """Pick the worker count, honouring an explicit flag, then WIKI_N_JOBS, then core count.

    Returns ``(value, is_explicit)`` where *is_explicit* is True when the caller
    supplied ``--concurrent-blocks`` — used to decide whether to print a nudge.
    """
    if flag_value is not None:
        return max(1, flag_value), True
    if settings.n_jobs != -1:
        return max(1, settings.n_jobs), False
    return max(1, os.cpu_count() or 1), False


@extract_app.command("run")
def extract_run(
    job_name: Annotated[str, typer.Argument(help="Name of the extraction job")],
    dump: Annotated[Path | None, typer.Option("--dump", help="Path to dump file (auto-detected if omitted)")] = None,
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="Job database URL (default: job's built-in default)"),
    ] = None,
    tracking_db_url: Annotated[
        str | None,
        typer.Option("--tracking-db-url", help="Database URL for ExtractionRun rows (default: wiki.db)"),
    ] = None,
    concurrent_blocks: Annotated[
        int | None,
        typer.Option("--concurrent-blocks", help="Blocks to process simultaneously (default: all CPU cores)."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Stop after N blocks (debug: iterate on a job in seconds, not minutes)."),
    ] = None,
    log_every: Annotated[int, typer.Option("--log-every", help="Print a stats line every N blocks.")] = 500,
) -> None:
    """Run an extraction job against a dump file."""
    from wiki_dumps.dumps.paths import find_dump, index_path_for
    from wiki_dumps.extract.runner import run_extraction
    from wiki_dumps.jobs import discover_job_classes
    from wiki_dumps.settings import get_settings

    settings = get_settings()

    job_classes = discover_job_classes()
    if job_name not in job_classes:
        names = ", ".join(sorted(job_classes))
        console.print(f"[red]Unknown job: {job_name!r}. Available: {names}[/red]")
        raise typer.Exit(1)

    job_cls = job_classes[job_name]
    effective_db_url = db_url if db_url is not None else getattr(job_cls, "default_db_url", settings.database_url)
    job = job_cls(effective_db_url)
    console.print(f"[dim]Job DB: {effective_db_url}[/dim]")

    effective_tracking_url = tracking_db_url if tracking_db_url is not None else settings.database_url

    concurrent, is_explicit = _resolve_concurrent(concurrent_blocks, settings)
    if not is_explicit:
        source = "WIKI_N_JOBS" if settings.n_jobs != -1 else "cpu cores"
        console.print(
            f"[dim]Using {concurrent} worker process(es) from {source}; override with --concurrent-blocks[/dim]"
        )

    if dump is None:
        dump = find_dump(settings.dump_dir)
        if dump is None:
            console.print(f"[red]No dump files found in {settings.dump_dir}. Run 'wiki dump download' first.[/red]")
            raise typer.Exit(1)
        console.print(f"[dim]Using dump: {dump}[/dim]")

    index_path = index_path_for(dump)
    if not index_path.exists():
        console.print(f"[red]Index file not found: {index_path}[/red]")
        raise typer.Exit(1)

    run = run_extraction(  # type: ignore[arg-type]
        dump,
        index_path,
        job,
        concurrent_blocks=concurrent,
        limit=limit,
        log_every=log_every,
        tracking_db_url=effective_tracking_url,
    )
    console.print(
        f"[green]Extraction complete.[/green] Processed={run.pages_processed:,} Matched={run.pages_matched:,}"
    )


if __name__ == "__main__":
    app()
