# Example Output: Sci-Fi Research Schema

A worked example for extracting science fiction novels, films, and authors from Wikipedia.
See `src/wiki_dumps/jobs/scifi.py` for the full implementation.

---

## Shared helpers (import, don't copy-paste)

All extraction jobs use a shared module for the wikitext/infobox primitives.
The job file imports from it:

```python
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.extract.wikitext import (
    clean_list_field,   # "a,b" → pipe-separated, {{hlist|a|b}} → pipe-separated
    extract_year,       # "{{Start date|1959|8|17}}" → 1959
    first_sentence,     # first sentence of stripped prose
    infobox_value,      # wikicode + "author" → raw value from the first template
    strip_wikitext,     # "[[John Doe]]" → "John Doe"
)
```

The per-job `_YEAR_RE`, `_LIST_TEMPLATES`, `_BATCH_SIZE` constants are no longer
re-declared — they live in the shared module. See `docs/prompts/schema-generation.md`
for the canonical list.

---

## Prompt Used

> I want to extract science fiction content from Wikipedia to build a research database.
> I need:
>
> **Novels/novellas:** title, author(s), publication year, publisher, series, genres,
> preceded_by, followed_by, first-sentence description.
>
> **Films:** title, director(s), writer(s), release year, based_on, starring, first-sentence description.
>
> **Authors/writers:** title, full name, birth year, death year, nationality, genres, notable works.
>
> Generate `src/wiki_dumps/jobs/scifi.py` with a per-job `DeclarativeBase`, ORM models,
> category-based filters, and wikitext extraction. The tables are auto-created
> from the ORM models via `setup_schema()`.

---

## ORM Models

```python
# src/wiki_dumps/jobs/scifi.py  (abridged)

class ScifiBase(DeclarativeBase):
    """Declarative base for scifi job ORM models."""


class ScifiNovel(ScifiBase):
    __tablename__ = "scifi_novels"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    author: Mapped[str | None]          # pipe-separated when multiple
    pub_year: Mapped[int | None]
    publisher: Mapped[str | None]
    series: Mapped[str | None]
    genres: Mapped[str | None]          # pipe-separated
    preceded_by: Mapped[str | None]
    followed_by: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ScifiFilm(ScifiBase):
    __tablename__ = "scifi_films"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    director: Mapped[str | None]        # pipe-separated when multiple
    writer: Mapped[str | None]          # pipe-separated when multiple
    release_year: Mapped[int | None]
    based_on: Mapped[str | None]
    starring: Mapped[str | None]        # pipe-separated
    description: Mapped[str | None] = mapped_column(Text)  # first sentence


class ScifiAuthor(ScifiBase):
    __tablename__ = "scifi_authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    full_name: Mapped[str | None]
    birth_year: Mapped[int | None]
    death_year: Mapped[int | None]
    nationality: Mapped[str | None]
    genres: Mapped[str | None]          # pipe-separated
    notable_works: Mapped[str | None]   # pipe-separated
```

---

## Category Filters

```python
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
```

---

## Schema (auto-created)

```python
class ScifiJob:
    def setup_schema(self) -> None:
        ScifiBase.metadata.create_all(self._engine)
```

---

## CLI Usage

```bash
# Run the sci-fi extraction job (tables auto-created from the ORM models)
uv run wiki extract run scifi --concurrent-blocks 32

# Explore the database
sqlite3 data/databases/scifi.db ".tables"
sqlite3 data/databases/scifi.db "SELECT COUNT(*) FROM scifi_novels;"
sqlite3 data/databases/scifi.db "SELECT title, author, pub_year FROM scifi_novels LIMIT 10;"
sqlite3 data/databases/scifi.db "SELECT title, director, release_year FROM scifi_films LIMIT 10;"
sqlite3 data/databases/scifi.db "SELECT title, birth_year, notable_works FROM scifi_authors LIMIT 10;"

# Explore interactively
jupyter lab notebooks/scifi_eda.ipynb
```

---

## Notes on Quality

- Novels are matched by category (e.g. "1984 science fiction novels") — series entries
  and disambiguation pages may slip through; filter by checking for `{{Infobox book}}`
- Films are matched by category (e.g. "2001 science fiction films") — TV episodes and
  short films may be included; add a runtime or medium filter to restrict if needed
- Authors are matched by category (e.g. "American science fiction writers") — some
  authors who write across genres will match if they have at least one SF category
- `pub_year` falls back through `pub_date`, `published`, and `release_date` infobox keys
- `nationality` falls back from `nationality` to `birth_place` — post-process to
  normalize country names if you need consistent grouping
