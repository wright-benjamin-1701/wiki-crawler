"""Extraction job: philosophy.

Extracts philosophers, philosophical works, and philosophical traditions
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
from wiki_dumps.extract.wikitext import clean_list_field, extract_year, first_sentence, infobox_value, strip_wikitext
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Per-job declarative base
# ---------------------------------------------------------------------------


class PhilosophyBase(DeclarativeBase):
    """Declarative base for philosophy job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class Philosopher(PhilosophyBase):
    """A philosopher, ethicist, or political theorist."""

    __tablename__ = "philosophers"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    era: Mapped[str | None]  # Ancient, Medieval, Modern, Contemporary
    schools: Mapped[str | None]  # pipe-separated schools/traditions
    main_interests: Mapped[str | None]  # pipe-separated
    notable_ideas: Mapped[str | None]  # pipe-separated
    notable_works: Mapped[str | None]  # pipe-separated


class PhilosophicalWork(PhilosophyBase):
    """A philosophical text, treatise, or book."""

    __tablename__ = "philosophical_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    author: Mapped[str | None]
    pub_year: Mapped[int | None]
    subject: Mapped[str | None]  # branch of philosophy (ethics, metaphysics, …)
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class PhilosophicalTradition(PhilosophyBase):
    """A school of philosophical thought, movement, or tradition."""

    __tablename__ = "philosophical_traditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    region: Mapped[str | None]  # Western, Eastern, etc.
    era: Mapped[str | None]
    founders: Mapped[str | None]  # pipe-separated
    key_figures: Mapped[str | None]  # pipe-separated
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

_PHILOSOPHER_CATEGORY_RE = re.compile(r"\bphilosophers?\b", re.IGNORECASE)
_WORK_CATEGORY_RE = re.compile(
    r"philosophy\s+books?|works?\s+of\s+(?:\w+\s+)?philosophy|"
    r"philosophical\s+(?:texts?|works?|treatises?)|"
    r"works?\s+on\s+(?:ethics|logic|metaphysics|epistemology|aesthetics|ontology)",
    re.IGNORECASE,
)
_TRADITION_CATEGORY_RE = re.compile(
    r"philosophical\s+(?:schools?|traditions?|movements?)|"
    r"philosophy\s+(?:schools?|traditions?|movements?)|"
    r"schools?\s+of\s+thought",
    re.IGNORECASE,
)
# Well-known tradition titles matched directly so their pages are captured
_TRADITION_TITLES: frozenset[str] = frozenset(
    {
        "Stoicism",
        "Epicureanism",
        "Platonism",
        "Aristotelianism",
        "Neoplatonism",
        "Rationalism",
        "Empiricism",
        "Kantianism",
        "Utilitarianism",
        "Existentialism",
        "Phenomenology",
        "Analytic philosophy",
        "Continental philosophy",
        "Pragmatism",
        "Marxism",
        "Nihilism",
        "Absurdism",
        "Idealism",
        "Materialism",
        "Nominalism",
        "Philosophical realism",
        "Skepticism",
        "Naturalism",
        "Humanism",
        "Structuralism",
        "Poststructuralism",
        "Postmodernism",
        "Confucianism",
        "Taoism",
        "Zen",
        "Buddhism",
        "Hinduism",
        "Logical positivism",
        "Functionalism",
        "Hegelian dialectics",
        "Dialectical materialism",
        "Social contract",
        "Virtue ethics",
        "Deontology",
        "Consequentialism",
        "Moral relativism",
    }
)


def _is_philosopher(page: WikiPage) -> bool:
    return has_category_matching(page, _PHILOSOPHER_CATEGORY_RE)


def _is_philosophical_work(page: WikiPage) -> bool:
    return has_category_matching(page, _WORK_CATEGORY_RE)


def _is_philosophical_tradition(page: WikiPage) -> bool:
    return page.title in _TRADITION_TITLES or has_category_matching(page, _TRADITION_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class PhilosophyJob:
    """Extracts philosophers, philosophical works, and traditions into three tables."""

    name: str = "philosophy"
    default_db_url: str = "sqlite:///data/databases/philosophy.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[PhilosophyBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return _is_philosopher(page) or _is_philosophical_work(page) or _is_philosophical_tradition(page)

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)
        record: PhilosophyBase

        if _is_philosopher(page):
            record = Philosopher(
                page_id=page.page_id,
                title=page.title,
                full_name=strip_wikitext(infobox_value(wikicode, "name")),
                birth_year=extract_year(infobox_value(wikicode, "birth_date")),
                death_year=extract_year(infobox_value(wikicode, "death_date")),
                nationality=strip_wikitext(
                    infobox_value(wikicode, "nationality") or infobox_value(wikicode, "birth_place")
                ),
                era=strip_wikitext(infobox_value(wikicode, "era") or infobox_value(wikicode, "region")),
                schools=clean_list_field(
                    infobox_value(wikicode, "school_tradition")
                    or infobox_value(wikicode, "school")
                    or infobox_value(wikicode, "tradition")
                ),
                main_interests=clean_list_field(infobox_value(wikicode, "main_interests")),
                notable_ideas=clean_list_field(infobox_value(wikicode, "notable_ideas")),
                notable_works=clean_list_field(infobox_value(wikicode, "notable_works")),
            )
        elif _is_philosophical_work(page):
            record = PhilosophicalWork(
                page_id=page.page_id,
                title=page.title,
                author=clean_list_field(infobox_value(wikicode, "author") or infobox_value(wikicode, "authors")),
                pub_year=extract_year(
                    infobox_value(wikicode, "pub_date")
                    or infobox_value(wikicode, "published")
                    or infobox_value(wikicode, "year")
                ),
                subject=strip_wikitext(infobox_value(wikicode, "subject") or infobox_value(wikicode, "genre")),
                description=first_sentence(wikicode),
            )
        else:  # tradition
            record = PhilosophicalTradition(
                page_id=page.page_id,
                title=page.title,
                region=strip_wikitext(infobox_value(wikicode, "region")),
                era=strip_wikitext(infobox_value(wikicode, "era")),
                founders=clean_list_field(infobox_value(wikicode, "founders")),
                key_figures=clean_list_field(
                    infobox_value(wikicode, "notable_proponents") or infobox_value(wikicode, "key_people")
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
        PhilosophyBase.metadata.create_all(self._engine)
