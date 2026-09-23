"""Tests for the extraction framework."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wiki_dumps.extract.filters import (
    has_category,
    has_category_matching,
    is_article,
    is_not_redirect,
    title_matches,
)
from wiki_dumps.jobs.base_pages import BasePagesJob
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


def test_has_category_match(sample_wiki_page: WikiPage) -> None:
    assert has_category(sample_wiki_page, "Jazz musicians") is True


def test_has_category_case_insensitive(sample_wiki_page: WikiPage) -> None:
    assert has_category(sample_wiki_page, "jazz musicians") is True


def test_has_category_no_match(sample_wiki_page: WikiPage) -> None:
    assert has_category(sample_wiki_page, "Classical musicians") is False


def test_has_category_matching_regex(sample_wiki_page: WikiPage) -> None:
    assert has_category_matching(sample_wiki_page, r"[Jj]azz") is True


def test_has_category_matching_no_match(sample_wiki_page: WikiPage) -> None:
    assert has_category_matching(sample_wiki_page, r"Classical") is False


def test_title_matches(sample_wiki_page: WikiPage) -> None:
    assert title_matches(sample_wiki_page, r"Miles") is True
    assert title_matches(sample_wiki_page, r"Coltrane") is False


def test_is_article(sample_wiki_page: WikiPage) -> None:
    assert is_article(sample_wiki_page) is True


def test_is_not_redirect(sample_wiki_page: WikiPage) -> None:
    assert is_not_redirect(sample_wiki_page) is True


# ---------------------------------------------------------------------------
# BasePagesJob tests
# ---------------------------------------------------------------------------


def test_base_pages_job_matches_article(
    sample_wiki_page: WikiPage, sqlite_db_url: str
) -> None:
    job = BasePagesJob(sqlite_db_url)
    job.setup_schema()
    assert job.matches(sample_wiki_page) is True


def test_base_pages_job_not_matches_talk_page(sqlite_db_url: str) -> None:
    job = BasePagesJob(sqlite_db_url)
    job.setup_schema()
    talk_page = WikiPage(
        page_id=1000,
        namespace=1,  # Talk namespace
        title="Talk:Miles Davis",
        redirect_to=None,
        categories=(),
        wikitext="",
        revision_id=1,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        contributor=None,
    )
    assert job.matches(talk_page) is False


def test_base_pages_job_extract_writes_to_db(
    sample_wiki_page: WikiPage, sqlite_db_url: str
) -> None:
    from sqlalchemy import select

    from wiki_dumps.db.session import get_session, make_engine
    from wiki_dumps.jobs.base_pages import ArticlePage

    job = BasePagesJob(sqlite_db_url)
    job.setup_schema()
    job.extract(sample_wiki_page)
    job.flush()

    engine = make_engine(sqlite_db_url)
    with get_session(engine) as session:
        results = session.execute(select(ArticlePage)).scalars().all()
        assert len(results) == 1
        assert results[0].title == "Miles Davis"
        assert results[0].page_id == 42
        assert results[0].category_count == 3


def test_run_extraction(mini_dump_bz2: Path, mini_index_bz2: Path, sqlite_db_url: str) -> None:
    from wiki_dumps.extract.runner import run_extraction

    job = BasePagesJob(sqlite_db_url)
    run = run_extraction(mini_dump_bz2, mini_index_bz2, job, concurrent_blocks=1)
    assert run.pages_processed == 2
    assert run.status == "complete"
