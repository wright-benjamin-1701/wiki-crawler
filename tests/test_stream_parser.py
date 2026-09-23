"""Tests for the streaming XML parser."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from wiki_dumps.parse.stream import iter_pages_from_dump
from wiki_dumps.parse.types import WikiPage


def test_iter_pages_yields_wiki_pages(mini_dump_bz2: Path) -> None:
    pages = list(iter_pages_from_dump(mini_dump_bz2))
    assert len(pages) == 2
    assert all(isinstance(p, WikiPage) for p in pages)


def test_first_page_attributes(mini_dump_bz2: Path) -> None:
    pages = list(iter_pages_from_dump(mini_dump_bz2))
    test_page = next(p for p in pages if p.title == "Test Article")
    assert test_page.page_id == 1
    assert test_page.namespace == 0
    assert test_page.revision_id == 100
    assert test_page.contributor == "TestUser"
    assert test_page.redirect_to is None


def test_categories_extracted(mini_dump_bz2: Path) -> None:
    pages = list(iter_pages_from_dump(mini_dump_bz2))
    test_page = next(p for p in pages if p.title == "Test Article")
    assert "Test Category" in test_page.categories
    assert "Articles" in test_page.categories


def test_jazz_page(mini_dump_bz2: Path) -> None:
    pages = list(iter_pages_from_dump(mini_dump_bz2))
    jazz_page = next(p for p in pages if p.title == "Jazz")
    assert jazz_page.page_id == 2
    assert "Jazz music" in jazz_page.categories


def test_wiki_page_is_article(sample_wiki_page: WikiPage) -> None:
    assert sample_wiki_page.is_article is True


def test_wiki_page_is_not_redirect(sample_wiki_page: WikiPage) -> None:
    assert sample_wiki_page.is_redirect is False


def test_wiki_page_redirect() -> None:
    from datetime import datetime

    redirect_page = WikiPage(
        page_id=99,
        namespace=0,
        title="Miles Davis (musician)",
        redirect_to="Miles Davis",
        categories=(),
        wikitext="#REDIRECT [[Miles Davis]]",
        revision_id=1,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        contributor=None,
    )
    assert redirect_page.is_redirect is True
    assert redirect_page.redirect_to == "Miles Davis"
