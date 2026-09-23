"""Parallel extraction runner.

``concurrent_blocks`` blocks are processed simultaneously in separate worker
*processes* (not threads), bypassing the GIL for CPU-bound Python work such as
regex matching and mwparserfromhell parsing.

Each worker process owns its own SQLAlchemy engine and SQLite connection pool.
The ``spawn`` start method is used so forked processes never inherit an open
database connection. Concurrent SQLite writes are serialized by WAL mode;
``PRAGMA busy_timeout`` lets writers queue rather than raise immediately.

If a preprocessed raw file exists (``wiki dump preprocess``), bz2 decompression
is skipped entirely — blocks are read with a plain seek + read.
"""

from __future__ import annotations

import importlib
import multiprocessing
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from wiki_dumps.db.base import Base
from wiki_dumps.db.run_model import ExtractionRun
from wiki_dumps.db.session import get_session, make_engine
from wiki_dumps.dumps.git import get_git_commit
from wiki_dumps.dumps.index import parse_index
from wiki_dumps.dumps.preprocess import is_preprocessed, load_raw_index, raw_paths
from wiki_dumps.dumps.types import StreamBlock
from wiki_dumps.parse.stream import iter_pages_from_bytes, iter_pages_from_xml_bytes
from wiki_dumps.parse.types import WikiPage

console = Console()
logger = getLogger(__name__)

if TYPE_CHECKING:
    from wiki_dumps.extract.base import ExtractJob

# ---------------------------------------------------------------------------
# Per-process worker state (set by _init_worker in each spawned process)
# ---------------------------------------------------------------------------

_worker_job: ExtractJob | None = None


def _init_worker(class_path: str, db_url: str) -> None:
    """Initializer run once in each worker process.

    Accepts *class_path* as a dotted import string (e.g.
    ``"wiki_dumps.jobs.jazz.JazzJob"``) rather than the class object itself,
    so that pickling never needs to traverse SQLAlchemy's DeclarativeBase
    metaclass graph (which causes a C-level stack overflow on Python 3.14).

    Constructs a fresh job instance (and therefore a fresh SQLAlchemy engine
    and connection pool) so no state is shared with the parent process.
    """
    global _worker_job
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, class_name)
    _worker_job = factory(db_url)


# ---------------------------------------------------------------------------
# Block I/O helpers (run in worker processes)
# ---------------------------------------------------------------------------


def _read_block_bz2(articles_path: Path, block: StreamBlock) -> bytes:
    with articles_path.open("rb") as f:
        f.seek(block.start_offset)
        if block.end_offset == -1:
            return f.read()
        return f.read(block.end_offset - block.start_offset)


def _read_block_raw(raw_path: Path, offset: int, length: int) -> bytes:
    with raw_path.open("rb") as f:
        f.seek(offset)
        return f.read(length)


def _dispatch_pages(
    pages: list[WikiPage],
    job: ExtractJob,
    t0: float,
) -> tuple[int, int, float]:
    matched = 0
    for page in pages:
        if job.matches(page):
            job.extract(page)
            matched += 1
    job.flush()
    return len(pages), matched, time.monotonic() - t0


def _process_block_bz2(
    block: StreamBlock,
    articles_path: Path,
) -> tuple[int, int, float]:
    """Decompress one bz2 block and dispatch pages (worker-process entry point)."""
    assert _worker_job is not None, "_init_worker was not called"
    t0 = time.monotonic()
    compressed = _read_block_bz2(articles_path, block)
    pages = list(iter_pages_from_bytes(compressed))
    del compressed
    return _dispatch_pages(pages, _worker_job, t0)


def _process_block_raw(
    raw_path: Path,
    offset: int,
    length: int,
) -> tuple[int, int, float]:
    """Read one raw block (no decompression) and dispatch pages (worker-process entry point)."""
    assert _worker_job is not None, "_init_worker was not called"
    t0 = time.monotonic()
    xml_bytes = _read_block_raw(raw_path, offset, length)
    pages = list(iter_pages_from_xml_bytes(xml_bytes))
    del xml_bytes
    return _dispatch_pages(pages, _worker_job, t0)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_extraction(
    dump_path: Path,
    index_path: Path,
    job: ExtractJob,
    *,
    concurrent_blocks: int = 1,
    log_every: int = 500,
    limit: int | None = None,
    tracking_db_url: str | None = None,
) -> ExtractionRun:
    """Run an extraction job over a multistream dump.

    Automatically uses the preprocessed raw file if present (``wiki dump preprocess``),
    otherwise falls back to bz2 decompression. Processes ``concurrent_blocks``
    blocks simultaneously in separate worker processes (true parallelism — no GIL).

    Parameters
    ----------
    dump_path:
        Path to the .xml.bz2 multistream articles file.
    index_path:
        Path to the corresponding .txt.bz2 multistream index file.
    job:
        An object satisfying the ExtractJob Protocol.
    concurrent_blocks:
        How many blocks to process at the same time (one OS process each).
    log_every:
        Print a stats line every N completed blocks.
    limit:
        Stop after processing this many blocks (for fast iteration when
        tweaking a job). ``None`` means process the entire dump.
    """
    job.setup_schema()

    blocks = parse_index(index_path)
    if limit is not None and limit > 0:
        blocks = blocks[:limit]
    n_blocks = len(blocks)
    started_at = datetime.now(tz=UTC)

    # Detect preprocessed raw file
    raw_path: Path | None = None
    raw_index: list[tuple[int, int]] | None = None
    if is_preprocessed(dump_path):
        raw_p, idx_p = raw_paths(dump_path)
        raw_index = load_raw_index(idx_p)
        raw_path = raw_p
        mode_label = "[green]raw[/green] (preprocessed, no bz2)"
    else:
        mode_label = "[yellow]bz2[/yellow] (run 'wiki dump preprocess' to speed up)"

    console.print(
        f"Starting [bold]{job.name}[/bold] | "
        f"{concurrent_blocks} worker process(es) | {n_blocks:,} blocks | {mode_label}"
    )

    total_processed = 0
    total_matched = 0
    blocks_done = 0
    blocks_failed = 0
    t_start = time.monotonic()

    # Each worker calls _init_worker to build its own fresh job instance with its
    # own engine — no shared connection state between processes.
    mp_ctx = multiprocessing.get_context("spawn")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[cyan]{task.fields[blk_per_s]:.1f}[/cyan] blk/s"),
        TextColumn("[cyan]{task.fields[pg_per_s]:,.0f}[/cyan] pg/s"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("| [green]{task.fields[matched]:,}[/green] matched"),
        console=console,
        refresh_per_second=2,
    ) as progress:
        task = progress.add_task(job.name, total=n_blocks, matched=0, blk_per_s=0.0, pg_per_s=0.0)

        with ProcessPoolExecutor(
            max_workers=concurrent_blocks,
            mp_context=mp_ctx,
            initializer=_init_worker,
            initargs=(f"{type(job).__module__}.{type(job).__qualname__}", job.db_url),
        ) as block_executor:
            futures: dict[Future[tuple[int, int, float]], int] = {}
            for i, block in enumerate(blocks):
                if raw_path is not None and raw_index is not None:
                    offset, length = raw_index[i]
                    f: Future[tuple[int, int, float]] = block_executor.submit(
                        _process_block_raw, raw_path, offset, length
                    )
                else:
                    f = block_executor.submit(_process_block_bz2, block, dump_path)
                futures[f] = i

            for future in as_completed(futures):
                block_idx = futures[future]
                try:
                    processed, matched, block_s = future.result()
                except Exception as exc:
                    blocks_failed += 1
                    blocks_done += 1
                    logger.warning("block %d failed: %s: %s", block_idx, type(exc).__name__, exc)
                    progress.update(task, advance=1)
                    continue

                total_processed += processed
                total_matched += matched
                blocks_done += 1

                wall = time.monotonic() - t_start
                blk_per_s = blocks_done / wall if wall > 0 else 0.0
                pg_per_s = total_processed / wall if wall > 0 else 0.0

                progress.update(
                    task,
                    advance=1,
                    matched=total_matched,
                    blk_per_s=blk_per_s,
                    pg_per_s=pg_per_s,
                )

                if blocks_done % log_every == 0 or blocks_done == n_blocks:
                    pct = 100.0 * blocks_done / n_blocks
                    console.log(
                        f"[dim]{blocks_done:,}/{n_blocks:,}[/dim] ({pct:.1f}%) | "
                        f"[cyan]{blk_per_s:.2f} blk/s | {pg_per_s:,.0f} pg/s[/cyan] | "
                        f"[green]{total_matched:,} matched[/green] | "
                        f"last block: {processed}p {matched}m {block_s * 1000:.0f}ms"
                    )

    completed_at = datetime.now(tz=UTC)
    wall_total = time.monotonic() - t_start
    failed_note = f" [yellow]({blocks_failed} blocks failed)[/yellow]" if blocks_failed else ""
    console.print(
        f"[bold green]Done.[/bold green] {total_processed:,} pages in {wall_total:.1f}s "
        f"({total_processed / wall_total:,.0f} pg/s) — [green]{total_matched:,}[/green] matched" + failed_note
    )

    _tracking_url = tracking_db_url if tracking_db_url is not None else job.db_url
    engine = make_engine(_tracking_url)
    Base.metadata.create_all(engine)
    run = ExtractionRun(
        started_at=started_at,
        completed_at=completed_at,
        dump_url=str(dump_path),
        dump_date=dump_path.name.split("-")[1] if "-" in dump_path.name else "unknown",
        schema_git_commit=get_git_commit(),
        schema_name=job.name,
        pages_processed=total_processed,
        pages_matched=total_matched,
        status="complete" if blocks_failed == 0 else "partial",
        error_message=f"{blocks_failed} block(s) failed (XML parse or other error)" if blocks_failed else None,
    )
    with get_session(engine, expire_on_commit=False) as session:
        session.add(run)

    return run
