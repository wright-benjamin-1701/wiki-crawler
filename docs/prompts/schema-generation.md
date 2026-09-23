# Prompt: Generate a New Extraction Schema

Use this prompt template with any LLM (Claude, GPT-4, Gemini, etc.) to generate
a complete `ExtractJob` implementation for a new Wikipedia research use case.

---

## System / Role Context

You are an expert Python developer specializing in SQLAlchemy 2.x and data pipeline
engineering. You write strongly typed code compatible with Pyright in strict mode.

---

## Codebase Context

Paste this into your prompt:

```python
# wiki_dumps/parse/types.py
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class WikiPage:
    page_id: int
    namespace: int
    title: str
    redirect_to: str | None
    categories: tuple[str, ...]
    wikitext: str
    revision_id: int
    timestamp: datetime
    contributor: str | None

    @property
    def is_article(self) -> bool: return self.namespace == 0

    @property
    def is_redirect(self) -> bool: return self.redirect_to is not None


# wiki_dumps/extract/base.py
from typing import Protocol

class ExtractJob(Protocol):
    name: str
    db_url: str
    default_db_url: str   # job's own default, e.g. "sqlite:///data/databases/jazz.db"
    def matches(self, page: WikiPage) -> bool: ...
    def extract(self, page: WikiPage) -> None: ...
    def setup_schema(self) -> None: ...


# Each job defines its own DeclarativeBase subclass for isolated SQLAlchemy metadata:
from sqlalchemy.orm import DeclarativeBase

class MyJobBase(DeclarativeBase):
    """Declarative base for my_job ORM models — keeps metadata isolated."""


# Available filter helpers (wiki_dumps/extract/filters.py):
# - has_category(page, category, *, case_sensitive=False) -> bool
# - has_category_matching(page, pattern) -> bool   # pattern = str regex or re.Pattern
# - title_matches(page, pattern) -> bool
# - is_article(page) -> bool
# - is_not_redirect(page) -> bool
#
# Available shared wikitext helpers (wiki_dumps/extract/wikitext.py):
#   DO NOT re-implement any of these — import and call them instead:
# - infobox_value(wikicode, key) -> str | None          # first template's value for `key`
# - strip_wikitext(raw) -> str | None                   # scalar field -> plain prose
# - clean_list_field(raw) -> str | None                 # list field -> "a|b|c"
# - first_sentence(wikicode) -> str | None              # first sentence of stripped prose
# - extract_year(text) -> int | None                     # first 4-digit year (1000-2029)
```

---

## User Task Description

**[FILL IN: Describe what you want to build. Examples:]**

- "I want to extract all jazz-related Wikipedia pages to build a research tool and
  playlist recommendation engine. I need artist names, birth/death years, genres,
  instruments, and associated albums."

- "I want to build a database of all Wikipedia articles about programming languages,
  including paradigm, typing discipline, first appeared date, and designer."

- "I want to extract all articles about mountains, including elevation, location,
  first ascent date, and mountain range."

---

## Output Requirements

Generate the following, fully typed and Pyright-strict-compatible:

1. **Per-job `DeclarativeBase` subclass** — e.g. `class MyJobBase(DeclarativeBase): ...`
   All ORM models for this job inherit from it (not the shared `Base`).
2. **ORM models** — SQLAlchemy 2.x `Mapped[T]` / `mapped_column` style
3. **`matches()` implementation** — using filter helpers to identify relevant pages
4. **`extract()` implementation** — parsing wikitext with `mwparserfromhell`;
   **import** the shared helpers (see the "Shared helpers" section) for scalar,
   list, year, and first-sentence fields
5. **Complete job module** — the full `src/wiki_dumps/jobs/<name>.py` file, including
   `default_db_url: str = "sqlite:///data/databases/<name>.db"` class attribute
6. **CLI example**:
   ```bash
   uv run wiki extract run <job-name> --concurrent-blocks 16
   ```

---

## Constraints

- All ORM columns must use `Mapped[T]` syntax (not `Column(Type)`)
- `extract()` must be idempotent or handle duplicates gracefully
- `setup_schema()` must call `<MyJobBase>.metadata.create_all(self._engine)` —
  the runner calls this at the start of every job, creating the tables from the ORM models
- Use `mwparserfromhell.parse(page.wikitext)` to extract structured data from wikitext
- Strip wikitext markup from scalar fields; pipe-separate list fields
- Nullable fields should be typed `Mapped[str | None]`
- The job class must satisfy the `ExtractJob` Protocol including `default_db_url`
- There is no migration layer — the schema is the ORM models, created via `setup_schema()`

---

## Batching Pattern (Required)

Every job must buffer records and write in batches for performance on large dumps.
Copy only the buffering *structure* below — the shared helpers and the batch size
are **imported**, never re-declared:

```python
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.extract.wikitext import (
    clean_list_field,
    extract_year,
    first_sentence,
    infobox_value,
    strip_wikitext,
)


class MyJob:
    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[MyJobBase] = []

    def extract(self, page: WikiPage) -> None:
        wikicode = mwparserfromhell.parse(page.wikitext)
        record = MyModel(
            title=page.title,
            year=extract_year(infobox_value(wikicode, "year")),
            name=strip_wikitext(infobox_value(wikicode, "name")),
            tags=clean_list_field(infobox_value(wikicode, "tags")),
            blurb=first_sentence(wikicode),
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
```

The runner calls `job.flush()` automatically after each block, so any records
buffered below the batch threshold are always committed.

**Do not** define your own `_BATCH_SIZE`, `_extract_year`, `_infobox_value`,
`_strip_wikitext`, `_clean_list_field`, `_first_sentence`, `_YEAR_RE`, or
`_LIST_TEMPLATES` — they already live in `wiki_dumps.extract.base` and
`wiki_dumps.extract.wikitext`. Only add job-local helpers for genuinely
domain-specific parsing (e.g. a `==Personnel==` section extractor).

---

## Session Import

```python
from wiki_dumps.db.session import get_session, make_engine
```

`get_session(engine)` is a context manager that commits on success and rolls back
on exception. Always use `session.add_all()` (not `session.add()`) for batches.

---

## Worked Example

See `docs/outputs/jazz-schema-example.md` for a complete generated job with all
models, helpers, and the `flush()` pattern applied.
