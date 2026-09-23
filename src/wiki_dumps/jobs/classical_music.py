"""Extraction job: classical music.

Extracts classical composers, musical compositions, and operas from Wikipedia
into three tables. Covers Infobox composer, Infobox musical composition,
and Infobox opera templates.
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
# Per-job declarative base
# ---------------------------------------------------------------------------


class ClassicalMusicBase(DeclarativeBase):
    """Declarative base for classical music job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class ClassicalComposer(ClassicalMusicBase):
    """A classical music composer from any era."""

    __tablename__ = "classical_composers"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    birth_place: Mapped[str | None]
    nationality: Mapped[str | None]
    era: Mapped[str | None]  # Baroque, Classical, Romantic, Modern, etc.
    genres: Mapped[str | None]  # pipe-separated
    notable_works: Mapped[str | None]  # pipe-separated


class ClassicalWork(ClassicalMusicBase):
    """A classical musical composition (symphony, concerto, sonata, quartet, etc.)."""

    __tablename__ = "classical_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    composer: Mapped[str | None]
    composed_year: Mapped[int | None]
    genre: Mapped[str | None]  # symphony, concerto, sonata, etc.
    key: Mapped[str | None]  # D minor, G major, etc.
    opus: Mapped[str | None]  # Op. 9, BWV 232, K. 525, etc.
    catalogue: Mapped[str | None]  # BWV, K., Op., Hob., etc.
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ClassicalOpera(ClassicalMusicBase):
    """An opera, operetta, or music drama."""

    __tablename__ = "classical_operas"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    composer: Mapped[str | None]
    librettist: Mapped[str | None]
    language: Mapped[str | None]
    premiere_year: Mapped[int | None]
    acts: Mapped[int | None]
    based_on: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_COMPOSER_CATEGORY_RE = re.compile(
    r"\bcomposers?\b",
    re.IGNORECASE,
)
_WORK_CATEGORY_RE = re.compile(
    r"\b(?:symphoni(?:es|a)|concertos?|sonatas?|string\s+quartets?|"
    r"piano\s+(?:trios?|quartets?|concertos?)|"
    r"chamber\s+music\s+works?|orchestral\s+works?|"
    r"cantatas?|oratorios?|requiems?|masses\s+\(music\)|"
    r"musical\s+compositions?)\b",
    re.IGNORECASE,
)
_OPERA_CATEGORY_RE = re.compile(
    r"\boperas?\b|\boperet(?:ta|tas?)\b|\bmusic\s+dramas?\b",
    re.IGNORECASE,
)


def _is_classical_composer(page: WikiPage) -> bool:
    return has_category_matching(page, _COMPOSER_CATEGORY_RE)


def _is_classical_work(page: WikiPage) -> bool:
    return has_category_matching(page, _WORK_CATEGORY_RE)


def _is_classical_opera(page: WikiPage) -> bool:
    return has_category_matching(page, _OPERA_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_ACTS_RE = re.compile(r"\b([1-9])\b")


def _extract_acts(text: str | None) -> int | None:
    if not text:
        return None
    m = _ACTS_RE.search(text)
    return int(m.group()) if m else None


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class ClassicalMusicJob:
    """Extracts classical composers, compositions, and operas into three tables."""

    name: str = "classical_music"
    default_db_url: str = "sqlite:///data/databases/classical_music.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[ClassicalMusicBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_classical_composer(page) or _is_classical_opera(page) or _is_classical_work(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: ClassicalMusicBase

        if _is_classical_opera(page):
            record = ClassicalOpera(
                page_id=page.page_id,
                title=page.title,
                composer=strip_wikitext(infobox_value(wikicode, "music")),
                librettist=strip_wikitext(infobox_value(wikicode, "libretto")),
                language=strip_wikitext(infobox_value(wikicode, "language")),
                premiere_year=extract_year(
                    infobox_value(wikicode, "premiere_date")
                    or infobox_value(wikicode, "premiere")
                    or infobox_value(wikicode, "date")
                ),
                acts=_extract_acts(infobox_value(wikicode, "acts")),
                based_on=strip_wikitext(infobox_value(wikicode, "based_on")),
                description=first_sentence(wikicode),
            )
        elif _is_classical_composer(page):
            record = ClassicalComposer(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                birth_place=strip_wikitext(infobox_value(wikicode, "birth_place")),
                nationality=strip_wikitext(infobox_value(wikicode, "nationality") or infobox_value(wikicode, "origin")),
                era=strip_wikitext(infobox_value(wikicode, "era") or infobox_value(wikicode, "period")),
                genres=clean_list_field(infobox_value(wikicode, "genre")),
                notable_works=clean_list_field(
                    infobox_value(wikicode, "notable_works") or infobox_value(wikicode, "works")
                ),
            )
        else:  # musical work
            record = ClassicalWork(
                page_id=page.page_id,
                title=page.title,
                composer=strip_wikitext(infobox_value(wikicode, "composer") or infobox_value(wikicode, "Composer")),
                composed_year=extract_year(
                    infobox_value(wikicode, "composed")
                    or infobox_value(wikicode, "date")
                    or infobox_value(wikicode, "year")
                ),
                genre=strip_wikitext(
                    infobox_value(wikicode, "type")
                    or infobox_value(wikicode, "genre")
                    or infobox_value(wikicode, "form")
                ),
                key=strip_wikitext(infobox_value(wikicode, "key") or infobox_value(wikicode, "tonality")),
                opus=strip_wikitext(
                    infobox_value(wikicode, "opus")
                    or infobox_value(wikicode, "catalogue")
                    or infobox_value(wikicode, "catalog")
                ),
                catalogue=strip_wikitext(infobox_value(wikicode, "catalogue") or infobox_value(wikicode, "catalog")),
                description=first_sentence(wikicode),
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
        ClassicalMusicBase.metadata.create_all(self._engine)
