# Example Output: Jazz Research Schema

This is an example of what the jazz research tool prompt (see `docs/prompts/jazz-example.md`)
produces when run through a capable LLM. Use this as a reference for what to expect
and as a starting point to customize.

---

## ORM Models

```python
# src/wiki_dumps/jobs/jazz.py
"""Extraction job: jazz research and playlist tool."""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wiki_dumps.db.session import get_session, make_engine
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.extract.filters import has_category_matching, is_article
from wiki_dumps.extract.wikitext import (
    clean_list_field,
    extract_year,
    infobox_value,
    strip_wikitext,
)
from wiki_dumps.parse.types import WikiPage


class JazzBase(DeclarativeBase):
    """Declarative base for jazz job ORM models."""


class JazzArtist(JazzBase):
    __tablename__ = "jazz_artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]                     # Wikipedia page title
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    instruments: Mapped[str | None]        # pipe-separated
    genres: Mapped[str | None]             # pipe-separated
    active_years_start: Mapped[int | None]
    active_years_end: Mapped[int | None]
    labels: Mapped[str | None]             # pipe-separated


class JazzAlbum(JazzBase):
    __tablename__ = "jazz_albums"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    artist: Mapped[str | None]
    release_year: Mapped[int | None]
    label: Mapped[str | None]
    genres: Mapped[str | None]             # pipe-separated
    personnel: Mapped[str | None] = mapped_column(Text)


class JazzGenre(JazzBase):
    __tablename__ = "jazz_genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    parent_genre: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


# ... filter helpers, extraction helpers, job class omitted for brevity
# See src/wiki_dumps/jobs/jazz.py for full implementation


class JazzResearchJob:
    name: str = "jazz"
    default_db_url: str = "sqlite:///data/databases/jazz.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)

    def matches(self, page: WikiPage) -> bool: ...
    def extract(self, page: WikiPage) -> None: ...

    def setup_schema(self) -> None:
        JazzBase.metadata.create_all(self._engine)
```

---

## Schema (auto-created)

There is no migration layer. The `setup_schema()` method creates the tables
directly from the ORM models above when the runner starts a job:

```python
class JazzJob:
    def setup_schema(self) -> None:
        JazzBase.metadata.create_all(self._engine)
```

---

## CLI Usage

```bash
# Download the latest English Wikipedia dump
uv run wiki dump download --lang en

# Optional: preprocess for ~3x faster extraction
uv run wiki dump preprocess data/dumps/enwiki-*-pages-articles-multistream.xml.bz2

# Run the jazz extraction job with 32 worker processes
# (tables are auto-created from the ORM models on first run)
uv run wiki extract run jazz --concurrent-blocks 32

# Check the resulting database
sqlite3 data/databases/jazz.db "SELECT COUNT(*) FROM jazz_artists;"
sqlite3 data/databases/jazz.db "SELECT title, birth_year, instruments FROM jazz_artists LIMIT 10;"

# Explore with the notebook
jupyter lab notebooks/eda.ipynb
```

---

## Notes on Quality

- The infobox field names (`birth_date`, `instrument`, etc.) come from Wikipedia's
  `{{Infobox musical artist}}` template — check the template documentation for the
  full list of available fields
- Some artists use `{{Infobox person}}` instead — add fallback key lookups
- Genre extraction is imprecise — many jazz pages don't use a genre infobox
- Consider adding a `raw_categories` column for downstream analysis
- `active_years_end` is always NULL — the `years_active` field (e.g. "1943–present")
  requires range parsing; prototype this in `notebooks/eda.ipynb` before adding to the job
