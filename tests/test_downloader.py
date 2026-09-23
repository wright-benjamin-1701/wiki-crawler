"""Tests for the dump downloader utilities."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pytest_httpx import HTTPXMock

from wiki_dumps import __version__
from wiki_dumps.dumps.downloader import HEADERS, USER_AGENT, download_dump, make_dump_file
from wiki_dumps.dumps.types import DumpFile


def test_make_dump_file_attributes(tmp_path: Path) -> None:
    dump = make_dump_file("en", "20240101", tmp_path)
    assert isinstance(dump, DumpFile)
    assert dump.lang == "en"
    assert dump.dump_date == date(2024, 1, 1)
    assert "enwiki-20240101" in dump.articles_url
    assert "enwiki-20240101" in dump.index_url


def test_make_dump_file_paths(tmp_path: Path) -> None:
    dump = make_dump_file("de", "20240201", tmp_path)
    assert dump.articles_path.parent == tmp_path
    assert dump.index_path.parent == tmp_path
    assert dump.articles_path.name.endswith(".xml.bz2")
    assert dump.index_path.name.endswith(".txt.bz2")


def test_is_downloaded_false_when_missing(tmp_path: Path) -> None:
    dump = make_dump_file("en", "20240101", tmp_path)
    assert dump.is_downloaded is False


def test_is_downloaded_true_when_present(tmp_path: Path) -> None:
    dump = make_dump_file("en", "20240101", tmp_path)
    dump.articles_path.write_bytes(b"fake")
    dump.index_path.write_bytes(b"fake")
    assert dump.is_downloaded is True


def test_user_agent_is_descriptive() -> None:
    # Wikimedia's nginx rejects the default `python-httpx` UA with 403.
    assert f"wiki-dumps/{__version__}" in USER_AGENT
    assert HEADERS["User-Agent"] == USER_AGENT
    assert "python-httpx" not in USER_AGENT


async def test_download_sends_user_agent(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """download_dump must send our descriptive User-Agent (not python-httpx)."""
    dump = make_dump_file("en", "20240101", tmp_path)
    dump.articles_path.unlink(missing_ok=True)
    dump.index_path.unlink(missing_ok=True)

    httpx_mock.add_response(method="GET", url=dump.articles_url, content=b"articles")
    httpx_mock.add_response(method="GET", url=dump.index_url, content=b"index")

    await download_dump(dump)

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    for req in requests:
        assert req.headers["user-agent"] == USER_AGENT
        assert "python-httpx" not in req.headers["user-agent"]
