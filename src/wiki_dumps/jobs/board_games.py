"""Extraction job: board games.

Extracts board games, tabletop game designers, and game publishers from Wikipedia
into three tables. Covers Infobox game and related templates.
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


class BoardGamesBase(DeclarativeBase):
    """Declarative base for board games job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class BoardGame(BoardGamesBase):
    """A board game, card game, or tabletop game."""

    __tablename__ = "board_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    designer: Mapped[str | None]  # pipe-separated when multiple
    publisher: Mapped[str | None]  # pipe-separated when multiple
    release_year: Mapped[int | None]
    min_players: Mapped[int | None]
    max_players: Mapped[int | None]
    play_time: Mapped[str | None]  # "30–120 minutes"
    age_range: Mapped[str | None]  # "10+"
    genres: Mapped[str | None]  # pipe-separated (strategy, party, co-op…)
    mechanics: Mapped[str | None]  # pipe-separated (dice rolling, deck building…)
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class GameDesigner(BoardGamesBase):
    """A tabletop game designer or creator."""

    __tablename__ = "game_designers"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    notable_games: Mapped[str | None]  # pipe-separated


class GamePublisher(BoardGamesBase):
    """A tabletop game publisher or studio."""

    __tablename__ = "game_publishers"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    country: Mapped[str | None]
    founded_year: Mapped[int | None]
    notable_games: Mapped[str | None]  # pipe-separated
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_GAME_CATEGORY_RE = re.compile(
    r"\b(?:board\s+games?|card\s+games?|tabletop\s+(?:role[\s-]playing\s+)?games?|"
    r"wargames?|eurogames?|abstract\s+strategy\s+games?|"
    r"party\s+games?|tile[\s-]based\s+games?|"
    r"miniature\s+wargames?|deck[\s-]building\s+games?|"
    r"cooperative\s+games?|trading\s+card\s+games?)\b",
    re.IGNORECASE,
)
_DESIGNER_CATEGORY_RE = re.compile(
    r"\b(?:board\s+game\s+designers?|game\s+designers?|"
    r"tabletop\s+game\s+(?:designers?|creators?))\b",
    re.IGNORECASE,
)
_PUBLISHER_CATEGORY_RE = re.compile(
    r"\b(?:board\s+game\s+(?:publishers?|companies?)|"
    r"game\s+publishers?|tabletop\s+(?:game\s+)?publishers?)\b",
    re.IGNORECASE,
)


def _is_board_game(page: WikiPage) -> bool:
    return has_category_matching(page, _GAME_CATEGORY_RE)


def _is_game_designer(page: WikiPage) -> bool:
    return has_category_matching(page, _DESIGNER_CATEGORY_RE)


def _is_game_publisher(page: WikiPage) -> bool:
    return has_category_matching(page, _PUBLISHER_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"\b(\d{1,2})\b")


def _extract_small_int(text: str | None) -> int | None:
    """Extract a small integer (player count, age) from a field value."""
    if not text:
        return None
    plain = mwparserfromhell.parse(text).strip_code().strip()
    m = _INT_RE.search(plain)
    if m:
        val = int(m.group())
        return val if val < 100 else None  # sanity check
    return None


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class BoardGamesJob:
    """Extracts board games, game designers, and game publishers into three tables."""

    name: str = "board_games"
    default_db_url: str = "sqlite:///data/databases/board_games.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[BoardGamesBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_board_game(page) or _is_game_designer(page) or _is_game_publisher(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: BoardGamesBase

        if _is_board_game(page):
            record = BoardGame(
                page_id=page.page_id,
                title=page.title,
                designer=clean_list_field(
                    infobox_value(wikicode, "designer")
                    or infobox_value(wikicode, "designers")
                    or infobox_value(wikicode, "author")
                ),
                publisher=clean_list_field(
                    infobox_value(wikicode, "publisher") or infobox_value(wikicode, "publishers")
                ),
                release_year=extract_year(
                    infobox_value(wikicode, "date")
                    or infobox_value(wikicode, "year")
                    or infobox_value(wikicode, "pub_date")
                ),
                min_players=_extract_small_int(infobox_value(wikicode, "min_players")),
                max_players=_extract_small_int(
                    infobox_value(wikicode, "max_players") or infobox_value(wikicode, "players")
                ),
                play_time=strip_wikitext(
                    infobox_value(wikicode, "playing_time") or infobox_value(wikicode, "play_time")
                ),
                age_range=strip_wikitext(infobox_value(wikicode, "ages") or infobox_value(wikicode, "age_range")),
                genres=clean_list_field(infobox_value(wikicode, "genre") or infobox_value(wikicode, "type")),
                mechanics=clean_list_field(infobox_value(wikicode, "mechanic") or infobox_value(wikicode, "mechanics")),
                description=first_sentence(wikicode),
            )
        elif _is_game_designer(page):
            record = GameDesigner(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                nationality=strip_wikitext(
                    infobox_value(wikicode, "nationality") or infobox_value(wikicode, "birth_place")
                ),
                notable_games=clean_list_field(
                    infobox_value(wikicode, "notable_works") or infobox_value(wikicode, "games")
                ),
            )
        else:  # publisher
            record = GamePublisher(
                page_id=page.page_id,
                title=page.title,
                country=strip_wikitext(
                    infobox_value(wikicode, "country")
                    or infobox_value(wikicode, "location")
                    or infobox_value(wikicode, "headquarters")
                ),
                founded_year=extract_year(
                    infobox_value(wikicode, "founded")
                    or infobox_value(wikicode, "foundation")
                    or infobox_value(wikicode, "established")
                ),
                notable_games=clean_list_field(
                    infobox_value(wikicode, "notable_works")
                    or infobox_value(wikicode, "games")
                    or infobox_value(wikicode, "products")
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
        BoardGamesBase.metadata.create_all(self._engine)
