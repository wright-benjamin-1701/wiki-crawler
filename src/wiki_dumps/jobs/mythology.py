"""Extraction job: mythology.

Extracts mythological deities, legendary creatures, and world mythologies
from Wikipedia into three tables.
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
from wiki_dumps.extract.wikitext import clean_list_field, first_sentence, infobox_value, strip_wikitext
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Per-job declarative base
# ---------------------------------------------------------------------------


class MythologyBase(DeclarativeBase):
    """Declarative base for mythology job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class MythDeity(MythologyBase):
    """A deity, god, goddess, or divine figure from world mythology."""

    __tablename__ = "myth_deities"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    mythology: Mapped[str | None]  # Greek, Norse, Egyptian, Hindu, etc.
    domains: Mapped[str | None]  # pipe-separated (war, love, wisdom…)
    symbols: Mapped[str | None]  # pipe-separated
    consort: Mapped[str | None]
    parents: Mapped[str | None]  # pipe-separated
    equivalents: Mapped[str | None]  # pipe-separated (Roman equivalents, etc.)
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class MythCreature(MythologyBase):
    """A legendary or mythological creature, monster, or being."""

    __tablename__ = "myth_creatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    mythology: Mapped[str | None]  # culture/tradition of origin
    classification: Mapped[str | None]  # dragon, giant, spirit, trickster, etc.
    first_appearance: Mapped[str | None]
    region: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class Mythology(MythologyBase):
    """A world mythology, religious tradition, or pantheon."""

    __tablename__ = "mythologies"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    culture: Mapped[str | None]  # Greek, Norse, Celtic, etc.
    region: Mapped[str | None]
    era: Mapped[str | None]
    key_figures: Mapped[str | None]  # pipe-separated major deities
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_CULTURES = (
    r"greek|roman|norse|egyptian|hindu|celtic|mesopotamian|aztec|mayan|"
    r"slavic|shinto|persian|sumerian|babylonian|japanese|chinese|"
    r"yoruba|polynesian|inuit|native\s+american|inca|aboriginal"
)

_DEITY_CATEGORY_RE = re.compile(
    rf"(?:{_CULTURES})\s+(?:deity|deities|god|goddess|gods|goddesses)|"
    r"deities\s+in|gods?\s+of\s+\w+",
    re.IGNORECASE,
)
_CREATURE_CATEGORY_RE = re.compile(
    r"(?:mytholog(?:ical|y)|legendary)\s+(?:creatures?|beings?|monsters?|animals?)|"
    r"creatures?\s+in\s+\w+\s+mythology|"
    r"monsters?\s+in\s+\w+\s+mythology",
    re.IGNORECASE,
)
_MYTHOLOGY_CATEGORY_RE = re.compile(
    rf"(?:{_CULTURES})\s+mythology|"
    r"world\s+mytholog(?:y|ies)|"
    r"(?:pantheons?|religious\s+traditions?)\s+by",
    re.IGNORECASE,
)
# Top-level mythology pages captured by title
_MYTHOLOGY_TITLES: frozenset[str] = frozenset(
    {
        "Greek mythology",
        "Roman mythology",
        "Norse mythology",
        "Egyptian mythology",
        "Hindu mythology",
        "Celtic mythology",
        "Mesopotamian mythology",
        "Aztec mythology",
        "Maya mythology",
        "Slavic mythology",
        "Shinto",
        "Persian mythology",
        "Sumerian mythology",
        "Babylonian mythology",
        "Japanese mythology",
        "Chinese mythology",
        "Yoruba religion",
        "Polynesian mythology",
        "Inuit mythology",
        "Inca mythology",
        "Aboriginal mythology",
        "Finnish mythology",
        "Armenian mythology",
        "Berber mythology",
    }
)


def _is_myth_deity(page: WikiPage) -> bool:
    return has_category_matching(page, _DEITY_CATEGORY_RE)


def _is_myth_creature(page: WikiPage) -> bool:
    return has_category_matching(page, _CREATURE_CATEGORY_RE)


def _is_mythology(page: WikiPage) -> bool:
    return page.title in _MYTHOLOGY_TITLES or has_category_matching(page, _MYTHOLOGY_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class MythologyJob:
    """Extracts mythological deities, creatures, and world mythologies into three tables."""

    name: str = "mythology"
    default_db_url: str = "sqlite:///data/databases/mythology.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[MythologyBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_myth_deity(page) or _is_myth_creature(page) or _is_mythology(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: MythologyBase

        if _is_myth_deity(page):
            record = MythDeity(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name") or infobox_value(wikicode, "god_of")),
                mythology=strip_wikitext(
                    infobox_value(wikicode, "religion")
                    or infobox_value(wikicode, "mythology")
                    or infobox_value(wikicode, "pantheon")
                ),
                domains=clean_list_field(
                    infobox_value(wikicode, "deity_of")
                    or infobox_value(wikicode, "god_of")
                    or infobox_value(wikicode, "member_of")
                ),
                symbols=clean_list_field(infobox_value(wikicode, "symbol")),
                consort=strip_wikitext(infobox_value(wikicode, "consort")),
                parents=clean_list_field(infobox_value(wikicode, "parents")),
                equivalents=clean_list_field(
                    infobox_value(wikicode, "Roman_equivalent")
                    or infobox_value(wikicode, "Greek_equivalent")
                    or infobox_value(wikicode, "equivalent")
                ),
                description=first_sentence(wikicode),
            )
        elif _is_myth_creature(page):
            record = MythCreature(
                page_id=page.page_id,
                title=page.title,
                mythology=strip_wikitext(
                    infobox_value(wikicode, "mythology")
                    or infobox_value(wikicode, "origin")
                    or infobox_value(wikicode, "Mythology")
                ),
                classification=strip_wikitext(
                    infobox_value(wikicode, "grouping") or infobox_value(wikicode, "classification")
                ),
                first_appearance=strip_wikitext(infobox_value(wikicode, "first_appearance")),
                region=strip_wikitext(infobox_value(wikicode, "region") or infobox_value(wikicode, "country")),
                description=first_sentence(wikicode),
            )
        else:  # mythology tradition
            record = Mythology(
                page_id=page.page_id,
                title=page.title,
                culture=strip_wikitext(infobox_value(wikicode, "culture") or infobox_value(wikicode, "region")),
                region=strip_wikitext(infobox_value(wikicode, "region") or infobox_value(wikicode, "geography")),
                era=strip_wikitext(infobox_value(wikicode, "period")),
                key_figures=clean_list_field(infobox_value(wikicode, "deities")),
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
        MythologyBase.metadata.create_all(self._engine)
