"""Extraction job: art history.

Extracts visual artists, artworks, and art movements from Wikipedia
into three tables. Covers Infobox artist, Infobox artwork, and related templates.
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


class ArtHistoryBase(DeclarativeBase):
    """Declarative base for art history job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class ArtArtist(ArtHistoryBase):
    """A visual artist — painter, sculptor, printmaker, or mixed-media artist."""

    __tablename__ = "art_artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    movements: Mapped[str | None]  # pipe-separated art movements
    medium: Mapped[str | None]  # pipe-separated (oil, watercolour, marble…)
    notable_works: Mapped[str | None]  # pipe-separated
    patrons: Mapped[str | None]  # pipe-separated


class ArtWork(ArtHistoryBase):
    """A specific artwork — painting, sculpture, drawing, or installation."""

    __tablename__ = "art_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    artist: Mapped[str | None]
    created_year: Mapped[int | None]
    medium: Mapped[str | None]  # oil on canvas, marble, bronze…
    dimensions: Mapped[str | None]  # e.g. "76 × 63 cm"
    location: Mapped[str | None]  # museum / collection
    movement: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ArtMovement(ArtHistoryBase):
    """An art movement, style, or school."""

    __tablename__ = "art_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    founding_year: Mapped[int | None]
    region: Mapped[str | None]
    key_artists: Mapped[str | None]  # pipe-separated
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_ARTIST_CATEGORY_RE = re.compile(
    r"\b(?:painters?|sculptors?|printmakers?|visual\s+artists?|"
    r"draughtsmen|draughtswomen|illustrators?|muralists?|engravers?)\b",
    re.IGNORECASE,
)
_ARTWORK_CATEGORY_RE = re.compile(
    r"\b(?:\d{4}\s+paintings?|paintings?\s+by|sculptures?\s+by|"
    r"artworks?\s+by|drawings?\s+by|lithographs?\s+by)\b",
    re.IGNORECASE,
)
_MOVEMENT_CATEGORY_RE = re.compile(
    r"\b(?:art\s+(?:movements?|styles?|schools?)|"
    r"artistic\s+(?:movements?|styles?|schools?))\b",
    re.IGNORECASE,
)
# Capture major movements directly by title
_MOVEMENT_TITLES: frozenset[str] = frozenset(
    {
        "Impressionism",
        "Post-Impressionism",
        "Cubism",
        "Surrealism",
        "Abstract expressionism",
        "Expressionism",
        "Fauvism",
        "Dadaism",
        "Futurism",
        "Constructivism",
        "Art Nouveau",
        "Art Deco",
        "Baroque",
        "Mannerism",
        "Romanticism",
        "Realism",
        "Neoclassicism",
        "Renaissance",
        "Symbolism",
        "Minimalism",
        "Pop art",
        "Conceptual art",
        "Performance art",
        "Street art",
        "Pointillism",
        "Naturalism",
        "Pre-Raphaelite Brotherhood",
        "De Stijl",
        "Bauhaus",
        "Fluxus",
        "Photorealism",
        "Op art",
    }
)


def _is_art_artist(page: WikiPage) -> bool:
    return has_category_matching(page, _ARTIST_CATEGORY_RE)


def _is_art_work(page: WikiPage) -> bool:
    return has_category_matching(page, _ARTWORK_CATEGORY_RE)


def _is_art_movement(page: WikiPage) -> bool:
    return page.title in _MOVEMENT_TITLES or has_category_matching(page, _MOVEMENT_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class ArtHistoryJob:
    """Extracts visual artists, artworks, and art movements into three tables."""

    name: str = "art_history"
    default_db_url: str = "sqlite:///data/databases/art_history.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[ArtHistoryBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_art_artist(page) or _is_art_work(page) or _is_art_movement(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: ArtHistoryBase

        if _is_art_work(page):
            record = ArtWork(
                page_id=page.page_id,
                title=page.title,
                artist=clean_list_field(infobox_value(wikicode, "artist") or infobox_value(wikicode, "Artist")),
                created_year=extract_year(
                    infobox_value(wikicode, "year")
                    or infobox_value(wikicode, "date")
                    or infobox_value(wikicode, "Year")
                ),
                medium=strip_wikitext(infobox_value(wikicode, "medium") or infobox_value(wikicode, "Medium")),
                dimensions=strip_wikitext(
                    infobox_value(wikicode, "dimensions") or infobox_value(wikicode, "height_metric")
                ),
                location=strip_wikitext(
                    infobox_value(wikicode, "museum")
                    or infobox_value(wikicode, "location")
                    or infobox_value(wikicode, "institution")
                ),
                movement=strip_wikitext(infobox_value(wikicode, "movement")),
                description=first_sentence(wikicode),
            )
        elif _is_art_artist(page):
            record = ArtArtist(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                nationality=strip_wikitext(
                    infobox_value(wikicode, "nationality") or infobox_value(wikicode, "birth_place")
                ),
                movements=clean_list_field(infobox_value(wikicode, "movement") or infobox_value(wikicode, "movements")),
                medium=clean_list_field(infobox_value(wikicode, "field") or infobox_value(wikicode, "medium")),
                notable_works=clean_list_field(
                    infobox_value(wikicode, "notable_works") or infobox_value(wikicode, "works")
                ),
                patrons=clean_list_field(infobox_value(wikicode, "patrons")),
            )
        else:  # art movement
            record = ArtMovement(
                page_id=page.page_id,
                title=page.title,
                founding_year=extract_year(
                    infobox_value(wikicode, "year")
                    or infobox_value(wikicode, "date")
                    or infobox_value(wikicode, "founded")
                ),
                region=strip_wikitext(infobox_value(wikicode, "country") or infobox_value(wikicode, "region")),
                key_artists=clean_list_field(
                    infobox_value(wikicode, "artists") or infobox_value(wikicode, "practitioners")
                ),
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
        ArtHistoryBase.metadata.create_all(self._engine)
