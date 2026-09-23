"""Extraction job: Star Trek franchise research.

Extracts Star Trek shows, episodes, movies, books, characters, species, and
starships into seven tables. Covers the full franchise: TOS through modern
streaming series, all films (prime and Kelvin timelines), novels, comics,
and the major recurring characters, alien species, and iconic starships.

Infobox templates covered:
- ``{{Star Trek episode}}`` / ``{{Infobox television episode}}``
- ``{{Infobox film}}``
- ``{{Infobox television}}``
- ``{{Infobox book}}``
- ``{{Star Trek character}}`` / ``{{Infobox character}}``
- ``{{Infobox fictional race}}`` / ``{{Star Trek species}}``
- ``{{Star Trek ship}}`` / ``{{Infobox fictional spacecraft}}``
"""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell  # type: ignore[import-untyped]
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wiki_dumps.db.session import get_session, make_engine
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.extract.filters import has_category, has_category_matching, is_article
from wiki_dumps.extract.wikitext import clean_list_field, extract_year, first_sentence, infobox_value, strip_wikitext
from wiki_dumps.parse.types import WikiPage

# ---------------------------------------------------------------------------
# Per-job declarative base (isolated metadata — only star_trek tables)
# ---------------------------------------------------------------------------


class StarTrekBase(DeclarativeBase):
    """Declarative base for Star Trek job ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class TrekShow(StarTrekBase):
    """A Star Trek television or streaming series."""

    __tablename__ = "trek_shows"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]  # Wikipedia page title
    abbreviation: Mapped[str | None]  # TOS, TNG, DS9, VOY, ENT, DIS, …
    premiere_year: Mapped[int | None]
    finale_year: Mapped[int | None]
    network: Mapped[str | None]  # CBS, Paramount+, NBC, …
    total_seasons: Mapped[int | None]
    total_episodes: Mapped[int | None]
    series_type: Mapped[str | None]  # live_action | animated
    description: Mapped[str | None] = mapped_column(Text)


class TrekEpisode(StarTrekBase):
    """A single Star Trek episode with its own Wikipedia page."""

    __tablename__ = "trek_episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    show_title: Mapped[str | None]  # e.g. "Star Trek: The Next Generation"
    season: Mapped[int | None]
    episode_number: Mapped[int | None]  # number within season
    production_code: Mapped[str | None]
    air_date: Mapped[str | None]  # raw string — "September 8, 1966"
    stardate: Mapped[str | None]
    director: Mapped[str | None]
    writer: Mapped[str | None]  # pipe-separated (teleplay + story)
    description: Mapped[str | None] = mapped_column(Text)


class TrekMovie(StarTrekBase):
    """A Star Trek feature film."""

    __tablename__ = "trek_movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    release_year: Mapped[int | None]
    director: Mapped[str | None]
    writer: Mapped[str | None]  # pipe-separated screenplay/story credits
    starring: Mapped[str | None]  # pipe-separated lead cast
    timeline: Mapped[str | None]  # prime | kelvin
    stardate: Mapped[str | None]
    box_office: Mapped[str | None]  # raw string (varies by source)
    budget: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


class TrekBook(StarTrekBase):
    """A Star Trek novel, novella, novelization, anthology, or comic."""

    __tablename__ = "trek_books"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    author: Mapped[str | None]  # pipe-separated
    series: Mapped[str | None]  # e.g. "New Frontier", "Destiny"
    publication_year: Mapped[int | None]
    publisher: Mapped[str | None]
    media_type: Mapped[str | None]  # novel | novelization | comic | anthology
    description: Mapped[str | None] = mapped_column(Text)


class TrekCharacter(StarTrekBase):
    """A Star Trek character (main cast or recurring)."""

    __tablename__ = "trek_characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]  # Wikipedia page title
    name: Mapped[str | None]  # character name from infobox
    portrayed_by: Mapped[str | None]  # pipe-separated actor(s)
    species: Mapped[str | None]
    rank: Mapped[str | None]  # e.g. "Captain", "Commander"
    affiliation: Mapped[str | None]  # pipe-separated organisations
    first_appearance: Mapped[str | None]  # show/episode title
    description: Mapped[str | None] = mapped_column(Text)


class TrekSpecies(StarTrekBase):
    """An alien species or civilisation in the Star Trek universe."""

    __tablename__ = "trek_species"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    quadrant: Mapped[str | None]  # Alpha | Beta | Gamma | Delta
    homeworld: Mapped[str | None]
    affiliation: Mapped[str | None]  # Federation, Klingon Empire, …
    description: Mapped[str | None] = mapped_column(Text)


class TrekStarship(StarTrekBase):
    """A named starship or space vessel from Star Trek."""

    __tablename__ = "trek_starships"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    ship_registry: Mapped[str | None] = mapped_column("registry")  # NCC-1701, NX-01, …
    ship_class: Mapped[str | None]  # Constitution, Galaxy, NX, …
    affiliation: Mapped[str | None]  # Starfleet, Klingon Empire, …
    first_appearance: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Filter patterns
# ---------------------------------------------------------------------------

# Known show titles → abbreviation (used both for matching and for lookup)
_SHOW_ABBREVIATIONS: dict[str, str] = {
    "Star Trek": "TOS",
    "Star Trek: The Animated Series": "TAS",
    "Star Trek: The Next Generation": "TNG",
    "Star Trek: Deep Space Nine": "DS9",
    "Star Trek: Voyager": "VOY",
    "Star Trek: Enterprise": "ENT",
    "Star Trek: Discovery": "DIS",
    "Star Trek: Picard": "PIC",
    "Star Trek: Strange New Worlds": "SNW",
    "Star Trek: Lower Decks": "LDS",
    "Star Trek: Prodigy": "PRO",
    "Star Trek: Section 31": "S31",
    "Star Trek: Starfleet Academy": "SFA",
}

# Kelvin-timeline film titles (everything else is prime)
_KELVIN_FILM_TITLES: frozenset[str] = frozenset(
    {
        "Star Trek (film)",
        "Star Trek Into Darkness",
        "Star Trek Beyond",
    }
)

# Episodes — "Star Trek: Deep Space Nine season 3 episodes", etc.
_EPISODE_CATEGORY_RE = re.compile(
    r"Star Trek[^)]*\s+(?:episodes?|season\s+\d+\s+episodes?)",
    re.IGNORECASE,
)

# Shows — "Star Trek television series" / "Star Trek animated series"
_SHOW_CATEGORY_RE = re.compile(
    r"Star Trek\s+(?:television|animated)\s+series",
    re.IGNORECASE,
)

# Books — novels, novelizations, comics, anthologies
_BOOK_CATEGORY_RE = re.compile(
    r"Star Trek\s+(?:novels?|books?|novelizations?|comics?|antholog)",
    re.IGNORECASE,
)

# Characters — "Star Trek characters", "Star Trek: TNG characters", etc.
_CHARACTER_CATEGORY_RE = re.compile(
    r"Star Trek.*\bcharacters?",
    re.IGNORECASE,
)
# Also catch pages categorised solely by in-universe species (e.g. "Fictional Vulcans")
_TREK_SPECIES_CHAR_RE = re.compile(
    r"Fictional\s+(?:Vulcans?|Klingons?|Romulans?|Cardassians?|Ferengi|"
    r"Bajorans?|Borg\b|Betazoids?|Andorians?|Trill\b|Xindi\b|Orions?)",
    re.IGNORECASE,
)

# Species — race/species articles
_SPECIES_CATEGORY_RE = re.compile(
    r"Star Trek\s+(?:races?|species|aliens?)|"
    r"(?:Extraterrestrial|Fictional)\s+(?:races?|species)\s+in\s+Star Trek",
    re.IGNORECASE,
)

# Starships
_STARSHIP_CATEGORY_RE = re.compile(
    r"Starships?\s+in\s+Star Trek|"
    r"Star Trek\s+starships?|"
    r"(?:Federation|Starfleet|Klingon|Romulan|Cardassian|Borg)\s+starships?",
    re.IGNORECASE,
)

# Sub-patterns for book media_type detection (compiled once)
_BOOK_NOVEL_RE = re.compile(r"Star Trek\s+novels?", re.IGNORECASE)
_BOOK_NOVELIZATION_RE = re.compile(r"Star Trek\s+novelizations?", re.IGNORECASE)
_BOOK_COMIC_RE = re.compile(r"Star Trek\s+comics?", re.IGNORECASE)
_BOOK_ANTHOLOGY_RE = re.compile(r"Star Trek\s+antholog", re.IGNORECASE)


def _is_trek_episode(page: WikiPage) -> bool:
    return has_category_matching(page, _EPISODE_CATEGORY_RE)


def _is_trek_movie(page: WikiPage) -> bool:
    return has_category(page, "Star Trek films")


def _is_trek_show(page: WikiPage) -> bool:
    return has_category_matching(page, _SHOW_CATEGORY_RE) or page.title in _SHOW_ABBREVIATIONS


def _is_trek_book(page: WikiPage) -> bool:
    return has_category_matching(page, _BOOK_CATEGORY_RE)


def _is_trek_character(page: WikiPage) -> bool:
    return has_category_matching(page, _CHARACTER_CATEGORY_RE) or has_category_matching(page, _TREK_SPECIES_CHAR_RE)


def _is_trek_species(page: WikiPage) -> bool:
    return has_category_matching(page, _SPECIES_CATEGORY_RE)


def _is_trek_starship(page: WikiPage) -> bool:
    return has_category_matching(page, _STARSHIP_CATEGORY_RE)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"\d+")
_EP_LIST_NAMES = frozenset({"episode list", "episode list/sublist"})
# Splits wikitext at season headings: == Season 1 (2020) == or === Season 2 ===
_SEASON_SPLIT_RE = re.compile(
    r"=+[ \t]*(?:Season|Part|Series)[ \t]+(\d+)[^=\n]*=+[ \t]*\n",
    re.IGNORECASE,
)


def _extract_int(text: str | None) -> int | None:
    """Parse the leading integer from *text* (handles '3', '4a', '4–6')."""
    if not text:
        return None
    m = _INT_RE.match(text.strip())
    return int(m.group()) if m else None


# ---------------------------------------------------------------------------
# Episode-list extraction from show pages
# ---------------------------------------------------------------------------


def _extract_episodes_from_show_page(show_page_id: int, show_title: str, wikitext: str) -> list[TrekEpisode]:
    """Parse ``{{Episode list}}`` templates embedded in a show page.

    Wikipedia show articles list every episode via ``{{Episode list}}`` (or its
    sublist variant) organised under ``== Season N ==`` headings.  We split on
    those headings so we can attach the correct season number to each row.
    """

    def _tmpl_str(tmpl: Any, key: str) -> str | None:
        return str(tmpl.get(key).value).strip() or None if tmpl.has(key) else None

    def _parse_section(text: str, season: int | None) -> list[TrekEpisode]:
        rows: list[TrekEpisode] = []
        code: Any = mwparserfromhell.parse(text)
        for tmpl in code.filter_templates():
            if str(tmpl.name).strip().lower() not in _EP_LIST_NAMES:
                continue
            title_raw = _tmpl_str(tmpl, "Title")
            if not title_raw:
                continue
            ep_title = mwparserfromhell.parse(title_raw).strip_code().strip()
            if not ep_title:
                continue
            rows.append(
                TrekEpisode(
                    page_id=show_page_id,
                    title=ep_title,
                    show_title=show_title,
                    season=season,
                    episode_number=_extract_int(_tmpl_str(tmpl, "EpisodeNumber2") or _tmpl_str(tmpl, "EpisodeNumber")),
                    production_code=strip_wikitext(_tmpl_str(tmpl, "ProdCode")),
                    air_date=strip_wikitext(_tmpl_str(tmpl, "OriginalAirDate")),
                    stardate=None,
                    director=strip_wikitext(_tmpl_str(tmpl, "DirectedBy")),
                    writer=clean_list_field(_tmpl_str(tmpl, "WrittenBy")),
                    description=strip_wikitext(_tmpl_str(tmpl, "ShortSummary")),
                )
            )
        return rows

    results: list[TrekEpisode] = []
    parts = _SEASON_SPLIT_RE.split(wikitext)
    if len(parts) > 1:
        # Odd indices are season numbers; even (>0) indices are section bodies.
        for i in range(1, len(parts), 2):
            season_no = int(parts[i])
            content = parts[i + 1] if i + 1 < len(parts) else ""
            results.extend(_parse_section(content, season_no))
    else:
        # No season headings — scan the whole page (e.g. mini-series).
        results.extend(_parse_section(wikitext, None))
    return results


# ---------------------------------------------------------------------------
# Per-entity extraction helpers
# ---------------------------------------------------------------------------


def _extract_show(page: WikiPage, wikicode: Any) -> TrekShow:
    series_type = (
        "animated"
        if has_category_matching(page, _SHOW_CATEGORY_RE) and "animated" in " ".join(page.categories).lower()
        else "live_action"
    )
    return TrekShow(
        page_id=page.page_id,
        title=page.title,
        abbreviation=_SHOW_ABBREVIATIONS.get(page.title),
        premiere_year=extract_year(infobox_value(wikicode, "first_aired") or infobox_value(wikicode, "premiere_date")),
        finale_year=extract_year(infobox_value(wikicode, "last_aired") or infobox_value(wikicode, "end_date")),
        network=strip_wikitext(infobox_value(wikicode, "network") or infobox_value(wikicode, "channel")),
        total_seasons=_extract_int(infobox_value(wikicode, "num_seasons")),
        total_episodes=_extract_int(infobox_value(wikicode, "num_episodes")),
        series_type=series_type,
        description=first_sentence(wikicode),
    )


def _extract_episode(page: WikiPage, wikicode: Any) -> TrekEpisode:
    # Merge teleplay + story into a single writer field
    teleplay = infobox_value(wikicode, "teleplay") or infobox_value(wikicode, "writer")
    story = infobox_value(wikicode, "story")
    if teleplay and story:
        writer_raw: str | None = teleplay + "\n" + story
    elif teleplay:
        writer_raw = teleplay
    else:
        writer_raw = story

    return TrekEpisode(
        page_id=page.page_id,
        title=page.title,
        show_title=strip_wikitext(infobox_value(wikicode, "series")),
        season=_extract_int(infobox_value(wikicode, "season")),
        episode_number=_extract_int(
            infobox_value(wikicode, "episode")
            or infobox_value(wikicode, "episode_no")
            or infobox_value(wikicode, "number")
        ),
        production_code=strip_wikitext(infobox_value(wikicode, "production")),
        air_date=strip_wikitext(infobox_value(wikicode, "airdate") or infobox_value(wikicode, "original_air_date")),
        stardate=strip_wikitext(infobox_value(wikicode, "stardate")),
        director=strip_wikitext(infobox_value(wikicode, "director")),
        writer=clean_list_field(writer_raw),
        description=first_sentence(wikicode),
    )


def _extract_movie(page: WikiPage, wikicode: Any) -> TrekMovie:
    return TrekMovie(
        page_id=page.page_id,
        title=page.title,
        release_year=extract_year(infobox_value(wikicode, "released") or infobox_value(wikicode, "release_date")),
        director=clean_list_field(infobox_value(wikicode, "director") or infobox_value(wikicode, "directed_by")),
        writer=clean_list_field(
            infobox_value(wikicode, "screenplay")
            or infobox_value(wikicode, "writer")
            or infobox_value(wikicode, "written_by")
        ),
        starring=clean_list_field(infobox_value(wikicode, "starring")),
        timeline="kelvin" if page.title in _KELVIN_FILM_TITLES else "prime",
        stardate=strip_wikitext(infobox_value(wikicode, "stardate")),
        box_office=strip_wikitext(infobox_value(wikicode, "gross") or infobox_value(wikicode, "box_office")),
        budget=strip_wikitext(infobox_value(wikicode, "budget")),
        description=first_sentence(wikicode),
    )


def _book_media_type(page: WikiPage) -> str | None:
    if has_category_matching(page, _BOOK_NOVELIZATION_RE):
        return "novelization"
    if has_category_matching(page, _BOOK_NOVEL_RE):
        return "novel"
    if has_category_matching(page, _BOOK_COMIC_RE):
        return "comic"
    if has_category_matching(page, _BOOK_ANTHOLOGY_RE):
        return "anthology"
    return None


def _extract_book(page: WikiPage, wikicode: Any) -> TrekBook:
    return TrekBook(
        page_id=page.page_id,
        title=page.title,
        author=clean_list_field(infobox_value(wikicode, "author") or infobox_value(wikicode, "authors")),
        series=strip_wikitext(infobox_value(wikicode, "series")),
        publication_year=extract_year(
            infobox_value(wikicode, "pub_date")
            or infobox_value(wikicode, "published")
            or infobox_value(wikicode, "release_date")
        ),
        publisher=strip_wikitext(infobox_value(wikicode, "publisher")),
        media_type=_book_media_type(page),
        description=first_sentence(wikicode),
    )


def _extract_character(page: WikiPage, wikicode: Any) -> TrekCharacter:
    return TrekCharacter(
        page_id=page.page_id,
        title=page.title,
        name=strip_wikitext(infobox_value(wikicode, "name") or infobox_value(wikicode, "character_name")),
        portrayed_by=clean_list_field(
            infobox_value(wikicode, "portrayed_by")
            or infobox_value(wikicode, "actor")
            or infobox_value(wikicode, "portrayer")
        ),
        species=strip_wikitext(infobox_value(wikicode, "species")),
        rank=strip_wikitext(infobox_value(wikicode, "rank") or infobox_value(wikicode, "title")),
        affiliation=clean_list_field(infobox_value(wikicode, "affiliation")),
        first_appearance=strip_wikitext(
            infobox_value(wikicode, "first") or infobox_value(wikicode, "first_appearance")
        ),
        description=first_sentence(wikicode),
    )


def _extract_species(page: WikiPage, wikicode: Any) -> TrekSpecies:
    return TrekSpecies(
        page_id=page.page_id,
        title=page.title,
        quadrant=strip_wikitext(infobox_value(wikicode, "quadrant") or infobox_value(wikicode, "region")),
        homeworld=strip_wikitext(infobox_value(wikicode, "homeworld") or infobox_value(wikicode, "home_world")),
        affiliation=clean_list_field(infobox_value(wikicode, "affiliation")),
        description=first_sentence(wikicode),
    )


def _extract_starship(page: WikiPage, wikicode: Any) -> TrekStarship:
    return TrekStarship(
        page_id=page.page_id,
        title=page.title,
        ship_registry=strip_wikitext(infobox_value(wikicode, "registry") or infobox_value(wikicode, "reg")),
        ship_class=strip_wikitext(
            infobox_value(wikicode, "class") or infobox_value(wikicode, "ship_class") or infobox_value(wikicode, "type")
        ),
        affiliation=clean_list_field(infobox_value(wikicode, "affiliation") or infobox_value(wikicode, "owner")),
        first_appearance=strip_wikitext(
            infobox_value(wikicode, "first") or infobox_value(wikicode, "first_appearance")
        ),
        description=first_sentence(wikicode),
    )


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class StarTrekJob:
    """Extracts Star Trek franchise data into seven tables.

    Tables: trek_shows, trek_episodes, trek_movies, trek_books,
    trek_characters, trek_species, trek_starships.
    """

    name: str = "star_trek"
    default_db_url: str = "sqlite:///data/databases/star_trek.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[StarTrekBase] = []

    def matches(self, page: WikiPage) -> bool:
        if not is_article(page):
            return False
        return (
            _is_trek_episode(page)
            or _is_trek_movie(page)
            or _is_trek_show(page)
            or _is_trek_book(page)
            or _is_trek_character(page)
            or _is_trek_species(page)
            or _is_trek_starship(page)
        )

    def extract(self, page: WikiPage) -> None:
        wikicode: Any = mwparserfromhell.parse(page.wikitext)

        # Priority: episode > movie > show > book > character > species > starship.
        # Character comes before species because many character pages (e.g. "Spock")
        # carry both "Star Trek characters" and "Fictional Vulcans" categories.
        if _is_trek_episode(page):
            self._pending.append(_extract_episode(page, wikicode))
        elif _is_trek_movie(page):
            self._pending.append(_extract_movie(page, wikicode))
        elif _is_trek_show(page):
            self._pending.append(_extract_show(page, wikicode))
            # Also mine the show page for episode titles via {{Episode list}}.
            # These rows use the show's page_id and fill in gaps for shows whose
            # individual episode pages weren't captured (Picard, Lower Decks, …).
            self._pending.extend(_extract_episodes_from_show_page(page.page_id, page.title, page.wikitext))
        elif _is_trek_book(page):
            self._pending.append(_extract_book(page, wikicode))
        elif _is_trek_character(page):
            self._pending.append(_extract_character(page, wikicode))
        elif _is_trek_species(page):
            self._pending.append(_extract_species(page, wikicode))
        else:
            self._pending.append(_extract_starship(page, wikicode))

        if len(self._pending) >= DEFAULT_BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        with get_session(self._engine) as session:
            session.add_all(self._pending)
        self._pending.clear()

    def setup_schema(self) -> None:
        StarTrekBase.metadata.create_all(self._engine)
