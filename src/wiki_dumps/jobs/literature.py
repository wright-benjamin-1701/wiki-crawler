"""Extraction job: literature.

Extracts literary novels, authors/poets, and poetry collections from Wikipedia
into three tables. Covers Infobox book, Infobox writer, and related templates.
"""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell  # type: ignore[import-untyped]
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wiki_dumps.db.session import get_session, make_engine
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.extract.filters import has_category_matching, is_article
from wiki_dumps.extract.wikitext import clean_list_field, extract_year, first_sentence, infobox_value, strip_wikitext
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Per-job declarative base (isolated metadata — only literature tables)
# ---------------------------------------------------------------------------


class LiteratureBase(DeclarativeBase):
    """Declarative base for literature job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class LitNovel(LiteratureBase):
    """A literary novel, novella, or work of fiction."""

    __tablename__ = "lit_novels"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    author: Mapped[str | None]  # pipe-separated when multiple
    pub_year: Mapped[int | None]
    publisher: Mapped[str | None]
    series: Mapped[str | None]
    genres: Mapped[str | None]  # pipe-separated
    language: Mapped[str | None]
    country: Mapped[str | None]
    preceded_by: Mapped[str | None]
    followed_by: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class LitAuthor(LiteratureBase):
    """A literary author, novelist, poet, or playwright."""

    __tablename__ = "lit_authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    genres: Mapped[str | None]  # pipe-separated
    notable_works: Mapped[str | None]  # pipe-separated
    awards: Mapped[str | None]  # pipe-separated
    movement: Mapped[str | None]


class LitPoetry(LiteratureBase):
    """A poetry collection, anthology, or book of poems."""

    __tablename__ = "lit_poetry"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    poet: Mapped[str | None]  # pipe-separated when multiple
    pub_year: Mapped[int | None]
    publisher: Mapped[str | None]
    language: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_NOVEL_CATEGORY_RE = re.compile(
    r"(?:English[\s-]language|American|British|Canadian|Australian|Irish|"
    r"French|German|Russian|Japanese|Indian|Chinese|Italian|Spanish|"
    r"Latin[\s-]American|African)\s+novels?|"
    r"\d{4}\s+novels?|novels?\s+by",
    re.IGNORECASE,
)
_AUTHOR_CATEGORY_RE = re.compile(
    r"novelists?|fiction\s+writers?|dramatists?|playwrights?|"
    r"short[- ]story\s+writers?|women\s+writers?|writers?\s+by",
    re.IGNORECASE,
)
_POETRY_CATEGORY_RE = re.compile(
    r"poetry\s+collections?|poems?\s+by|collections?\s+of\s+poems?|"
    r"poetry\s+books?|\d{4}\s+poetry",
    re.IGNORECASE,
)


def _is_lit_novel(page: WikiPage) -> bool:
    return has_category_matching(page, _NOVEL_CATEGORY_RE)


def _is_lit_author(page: WikiPage) -> bool:
    return has_category_matching(page, _AUTHOR_CATEGORY_RE)


def _is_lit_poetry(page: WikiPage) -> bool:
    return has_category_matching(page, _POETRY_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class LiteratureJob:
    """Extracts literary novels, authors/poets, and poetry collections into three tables."""

    name: str = "literature"
    default_db_url: str = "sqlite:///data/databases/literature.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[LiteratureBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_lit_novel(page) or _is_lit_author(page) or _is_lit_poetry(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: LiteratureBase

        if _is_lit_novel(page):
            record = LitNovel(
                page_id=page.page_id,
                title=page.title,
                author=clean_list_field(infobox_value(wikicode, "author") or infobox_value(wikicode, "authors")),
                pub_year=extract_year(
                    infobox_value(wikicode, "pub_date")
                    or infobox_value(wikicode, "published")
                    or infobox_value(wikicode, "release_date")
                ),
                publisher=strip_wikitext(infobox_value(wikicode, "publisher")),
                series=strip_wikitext(infobox_value(wikicode, "series")),
                genres=clean_list_field(infobox_value(wikicode, "genre")),
                language=strip_wikitext(infobox_value(wikicode, "language")),
                country=strip_wikitext(infobox_value(wikicode, "country")),
                preceded_by=strip_wikitext(infobox_value(wikicode, "preceded_by")),
                followed_by=strip_wikitext(infobox_value(wikicode, "followed_by")),
                description=first_sentence(wikicode),
            )
        elif _is_lit_poetry(page):
            record = LitPoetry(
                page_id=page.page_id,
                title=page.title,
                poet=clean_list_field(infobox_value(wikicode, "author") or infobox_value(wikicode, "poet")),
                pub_year=extract_year(infobox_value(wikicode, "pub_date") or infobox_value(wikicode, "published")),
                publisher=strip_wikitext(infobox_value(wikicode, "publisher")),
                language=strip_wikitext(infobox_value(wikicode, "language")),
                description=first_sentence(wikicode),
            )
        else:  # author / poet / playwright
            record = LitAuthor(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                nationality=strip_wikitext(
                    infobox_value(wikicode, "nationality") or infobox_value(wikicode, "birth_place")
                ),
                genres=clean_list_field(infobox_value(wikicode, "genre")),
                notable_works=clean_list_field(infobox_value(wikicode, "notable_works")),
                awards=clean_list_field(infobox_value(wikicode, "awards")),
                movement=strip_wikitext(infobox_value(wikicode, "movement")),
            )

        self._pending.append(record)
        if len(self._pending) >= DEFAULT_BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        with get_session(self._engine) as session:
            session.add_all(self._pending)
        self._pending.clear()

    def setup_schema(self) -> None:
        LiteratureBase.metadata.create_all(self._engine)
