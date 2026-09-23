# Example: Jazz Research Tool Prompt

This is a worked example showing how to fill in the schema-generation prompt template
for a jazz music research and playlist recommendation tool.

---

## Filled-in Prompt

**System:** You are an expert Python developer specializing in SQLAlchemy 2.x and data
pipeline engineering. You write strongly typed code compatible with Pyright in strict mode.

**User:**

I want to extract all jazz-related Wikipedia pages to build a research tool and playlist
recommendation engine. Specifically I need:

**Artists/Musicians:**
- Full name and Wikipedia page title
- Birth year, death year (nullable)
- Nationality/country
- Primary instrument(s)
- Associated genres (e.g. bebop, cool jazz, fusion)
- Active years (start, end nullable)
- Record labels they recorded for

**Albums:**
- Album title
- Artist name(s)
- Release year
- Record label
- Genre tags
- Personnel listed on the album

**Genres:**
- Genre name
- Parent genre (nullable)
- Brief description

Use the following codebase context:

```python
[paste WikiPage, ExtractJob, Base, and filter helpers as shown in schema-generation.md]
```

Generate the full `src/wiki_dumps/jobs/jazz.py` module with a per-job
`DeclarativeBase`, ORM models, matches() filter, and extract() implementation.
The tables are auto-created from the ORM models via `setup_schema()`.

---

## Why This is a Good Prompt

- **Specific fields**: Naming exact fields helps the LLM design appropriate ORM columns
- **Nullable awareness**: Mentioning "(nullable)" helps get `Mapped[str | None]` types
- **Multiple entity types**: The LLM will generate 3 ORM models (Artist, Album, Genre)
- **Use case context**: "playlist recommendation engine" helps the LLM prioritize fields

---

## Expected Output

See `docs/outputs/jazz-schema-example.md` for an example of what this prompt produces.
