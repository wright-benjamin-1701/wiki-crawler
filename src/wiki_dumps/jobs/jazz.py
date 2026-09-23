"""Extraction job: jazz research and playlist tool.

Extracts jazz artists, albums, and genres from Wikipedia into three tables.
Generated from docs/prompts/jazz-example.md.
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
from wiki_dumps.extract.wikitext import clean_list_field, extract_year, infobox_value, strip_wikitext
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Per-job declarative base (isolated metadata — only jazz tables)
# ---------------------------------------------------------------------------


class JazzBase(DeclarativeBase):
    """Declarative base for jazz job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class JazzArtist(JazzBase):
    """A jazz musician or vocalist."""

    __tablename__ = "jazz_artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]  # Wikipedia page title
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    instruments: Mapped[str | None]  # pipe-separated list
    genres: Mapped[str | None]  # pipe-separated list
    active_years_start: Mapped[int | None]
    active_years_end: Mapped[int | None]
    labels: Mapped[str | None]  # pipe-separated list


class JazzAlbum(JazzBase):
    """A jazz album or recording."""

    __tablename__ = "jazz_albums"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    artist: Mapped[str | None]
    release_year: Mapped[int | None]
    label: Mapped[str | None]
    genres: Mapped[str | None]  # pipe-separated list
    personnel: Mapped[str | None] = mapped_column(Text)  # raw wikitext personnel section


class JazzGenre(JazzBase):
    """A jazz genre or subgenre."""

    __tablename__ = "jazz_genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    parent_genre: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Filter logic
# ---------------------------------------------------------------------------

_ARTIST_CATEGORY_RE = re.compile(
    r"jazz\s+(musician|artist|singer|pianist|guitarist|drummer|bassist|"
    r"trumpeter|saxophonist|trombonist|vibraphonist|organist|composer)",
    re.IGNORECASE,
)
_ALBUM_CATEGORY_RE = re.compile(r"jazz\s+album", re.IGNORECASE)
_GENRE_TITLES: frozenset[str] = frozenset(
    {
        "Jazz",
        "Bebop",
        "Cool jazz",
        "Hard bop",
        "Free jazz",
        "Fusion jazz",
        "Soul jazz",
        "Modal jazz",
        "Swing music",
        "Dixieland",
        "Bossa nova",
        "Gypsy jazz",
        "Latin jazz",
        "Acid jazz",
        "Nu jazz",
        "Smooth jazz",
    }
)


def _is_jazz_artist(page: WikiPage) -> bool:
    return has_category_matching(page, _ARTIST_CATEGORY_RE)


def _is_jazz_album(page: WikiPage) -> bool:
    return has_category_matching(page, _ALBUM_CATEGORY_RE)


def _is_jazz_genre(page: WikiPage) -> bool:
    return page.title in _GENRE_TITLES or has_category_matching(page, r"(?i)jazz\s+genre")


# ---------------------------------------------------------------------------
# Job-local helpers (shared helpers live in wiki_dumps.extract.wikitext)
# ---------------------------------------------------------------------------

_PERSONNEL_SECTION_RE = re.compile(
    r"==\s*personnel\s*==\s*\n(.*?)(?=\n==|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_personnel_section(wikitext: str) -> str | None:
    """Return the raw wikitext of the ==Personnel== article section, if present."""
    m = _PERSONNEL_SECTION_RE.search(wikitext)
    if not m:
        return None
    return m.group(1).strip() or None


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class JazzJob:
    """Extracts jazz artists, albums, and genres into three SQLite/Postgres tables."""

    name: str = "jazz"
    default_db_url: str = "sqlite:///data/databases/jazz.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[JazzBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_jazz_artist(page) or _is_jazz_album(page) or _is_jazz_genre(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: JazzBase

        if _is_jazz_artist(page):
            record = JazzArtist(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                nationality=strip_wikitext(infobox_value(wikicode, "origin")),
                instruments=clean_list_field(infobox_value(wikicode, "instrument")),
                genres=clean_list_field(infobox_value(wikicode, "genre")),
                active_years_start=extract_year(infobox_value(wikicode, "years_active")),
                active_years_end=None,
                labels=clean_list_field(infobox_value(wikicode, "label")),
            )
        elif _is_jazz_album(page):
            record = JazzAlbum(
                page_id=page.page_id,
                title=page.title,
                artist=strip_wikitext(infobox_value(wikicode, "artist") or infobox_value(wikicode, "Artist")),
                release_year=extract_year(infobox_value(wikicode, "released")),
                label=clean_list_field(infobox_value(wikicode, "label")),
                genres=clean_list_field(infobox_value(wikicode, "genre")),
                personnel=(infobox_value(wikicode, "personnel") or _extract_personnel_section(page.wikitext)),
            )
        else:
            plain: str = wikicode.strip_code()
            description = plain.split(".")[0].strip() if plain else None
            record = JazzGenre(
                page_id=page.page_id,
                title=page.title,
                parent_genre=clean_list_field(infobox_value(wikicode, "stylistic_origins")),
                description=description or None,
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
        JazzBase.metadata.create_all(self._engine)
