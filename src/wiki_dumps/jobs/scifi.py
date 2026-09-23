"""Extraction job: science fiction research.

Extracts science fiction novels, films, and authors from Wikipedia into three
tables. Covers infobox templates: Infobox book, Infobox film, Infobox writer/person.
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
# Per-job declarative base (isolated metadata — only scifi tables)
# ---------------------------------------------------------------------------


class ScifiBase(DeclarativeBase):
    """Declarative base for scifi job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class ScifiNovel(ScifiBase):
    """A science fiction novel, novella, or short-story collection."""

    __tablename__ = "scifi_novels"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    author: Mapped[str | None]  # pipe-separated when multiple
    pub_year: Mapped[int | None]
    publisher: Mapped[str | None]
    series: Mapped[str | None]
    genres: Mapped[str | None]  # pipe-separated
    preceded_by: Mapped[str | None]
    followed_by: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ScifiFilm(ScifiBase):
    """A science fiction feature film or TV movie."""

    __tablename__ = "scifi_films"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    director: Mapped[str | None]  # pipe-separated when multiple
    writer: Mapped[str | None]  # pipe-separated when multiple
    release_year: Mapped[int | None]
    based_on: Mapped[str | None]
    starring: Mapped[str | None]  # pipe-separated
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ScifiAuthor(ScifiBase):
    """A science fiction writer or creator."""

    __tablename__ = "scifi_authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    genres: Mapped[str | None]  # pipe-separated
    notable_works: Mapped[str | None]  # pipe-separated


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_NOVEL_CATEGORY_RE = re.compile(
    r"science[- ]fiction\s+(?:novels?|novellas?|short[\s-]stor|antholog)",
    re.IGNORECASE,
)
_FILM_CATEGORY_RE = re.compile(
    r"science[- ]fiction\s+films?",
    re.IGNORECASE,
)
_AUTHOR_CATEGORY_RE = re.compile(
    r"science[- ]fiction\s+(?:writers?|authors?|novelists?)",
    re.IGNORECASE,
)


def _is_scifi_novel(page: WikiPage) -> bool:
    return has_category_matching(page, _NOVEL_CATEGORY_RE)


def _is_scifi_film(page: WikiPage) -> bool:
    return has_category_matching(page, _FILM_CATEGORY_RE)


def _is_scifi_author(page: WikiPage) -> bool:
    return has_category_matching(page, _AUTHOR_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class ScifiJob:
    """Extracts science fiction novels, films, and authors into three tables."""

    name: str = "scifi"
    default_db_url: str = "sqlite:///data/databases/scifi.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[ScifiBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_scifi_novel(page) or _is_scifi_film(page) or _is_scifi_author(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: ScifiBase

        if _is_scifi_novel(page):
            record = ScifiNovel(
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
                preceded_by=strip_wikitext(infobox_value(wikicode, "preceded_by")),
                followed_by=strip_wikitext(infobox_value(wikicode, "followed_by")),
                description=first_sentence(wikicode),
            )
        elif _is_scifi_film(page):
            record = ScifiFilm(
                page_id=page.page_id,
                title=page.title,
                director=clean_list_field(
                    infobox_value(wikicode, "director") or infobox_value(wikicode, "directed_by")
                ),
                writer=clean_list_field(
                    infobox_value(wikicode, "writer")
                    or infobox_value(wikicode, "screenplay")
                    or infobox_value(wikicode, "written_by")
                ),
                release_year=extract_year(
                    infobox_value(wikicode, "released") or infobox_value(wikicode, "release_date")
                ),
                based_on=strip_wikitext(infobox_value(wikicode, "based_on")),
                starring=clean_list_field(infobox_value(wikicode, "starring")),
                description=first_sentence(wikicode),
            )
        else:  # author
            record = ScifiAuthor(
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
        ScifiBase.metadata.create_all(self._engine)
