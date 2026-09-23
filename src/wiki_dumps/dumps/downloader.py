"""Async downloader for Wikipedia dump files with rich progress display."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from wiki_dumps import __version__ as _version
from wiki_dumps.dumps.types import DumpFile

_DUMPS_BASE = "https://dumps.wikimedia.org"
# Wikimedia's nginx rejects the default `python-httpx` User-Agent with 403; a
# descriptive, contactable UA is required per their robot policy.
USER_AGENT = f"wiki-dumps/{_version} (https://github.com/benwright/wiki-dumps)"
HEADERS = {"User-Agent": USER_AGENT}
_console = Console()


def make_dump_file(lang: str, dump_date: str, dump_dir: Path) -> DumpFile:
    """Construct a DumpFile for the given language and date string (YYYYMMDD or 'latest')."""
    from datetime import date as _date

    base = f"{_DUMPS_BASE}/{lang}wiki/{dump_date}"
    prefix = f"{lang}wiki-{dump_date}"
    articles_url = f"{base}/{prefix}-pages-articles-multistream.xml.bz2"
    index_url = f"{base}/{prefix}-pages-articles-multistream-index.txt.bz2"

    dump_dir.mkdir(parents=True, exist_ok=True)
    articles_path = dump_dir / f"{prefix}-pages-articles-multistream.xml.bz2"
    index_path = dump_dir / f"{prefix}-pages-articles-multistream-index.txt.bz2"

    parsed_date = _date.today() if dump_date == "latest" else _date(
        int(dump_date[:4]), int(dump_date[4:6]), int(dump_date[6:8])
    )
    return DumpFile(
        lang=lang,
        dump_date=parsed_date,
        articles_url=articles_url,
        index_url=index_url,
        articles_path=articles_path,
        index_path=index_path,
    )


async def _download_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    progress: Progress,
    task_id: TaskID,
) -> None:
    """Stream a single file from *url* to *dest*, updating *progress*."""
    async with client.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        progress.update(task_id, total=total)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                f.write(chunk)
                progress.advance(task_id, len(chunk))


async def download_dump(dump: DumpFile, *, force: bool = False) -> None:
    """Download the articles and index files for *dump*.

    Skips files that already exist unless *force* is True.
    """
    files_to_download: list[tuple[str, Path, str]] = []
    if force or not dump.articles_path.exists():
        files_to_download.append((dump.articles_url, dump.articles_path, "articles"))
    if force or not dump.index_path.exists():
        files_to_download.append((dump.index_url, dump.index_path, "index"))

    if not files_to_download:
        _console.print("[green]Both files already downloaded.[/green]")
        return

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=_console,
    ) as progress:
        async with httpx.AsyncClient(timeout=None, headers=HEADERS) as client:
            coros = [
                _download_file(client, url, dest, progress, progress.add_task(label, total=None))
                for url, dest, label in files_to_download
            ]
            await asyncio.gather(*coros)


async def _dump_is_complete(client: httpx.AsyncClient, lang: str, date: str) -> bool:
    """Return True if the multistream dump for *date* has finished generating.

    Checks the Wikimedia dumpstatus.json for the articlesmultistreamdump job.
    """
    url = f"{_DUMPS_BASE}/{lang}wiki/{date}/dumpstatus.json"
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code != 200:
            return False
        status = resp.json()
        job = status.get("jobs", {}).get("articlesmultistreamdump", {})
        return str(job.get("status", "")) == "done"
    except Exception:
        return False


async def list_available_dumps(lang: str = "en", *, completed_only: bool = True) -> list[str]:
    """Return a list of available dump dates for *lang*.

    When *completed_only* is True (default), only dates where the multistream
    dump has finished generating are returned.  This avoids 404 errors when
    the most-recent directory exists but the files aren't ready yet.
    """
    import re

    url = f"{_DUMPS_BASE}/{lang}wiki/"
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        dates = sorted(re.findall(r'href="(\d{8})/"', response.text))
        if not completed_only:
            return dates
        # Check the most recent ~5 dates for completion (avoids checking every date)
        candidates = dates[-5:]
        checks = await asyncio.gather(*[_dump_is_complete(client, lang, d) for d in candidates])
        completed = [d for d, ok in zip(candidates, checks) if ok]
        # Return all older dates (assumed complete) + verified recent ones
        return sorted(dates[:-5] + completed)
