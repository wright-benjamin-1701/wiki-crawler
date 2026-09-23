# Reference Commands

Quick reference for common wiki-dumps tasks. All commands assume you are in the repo root with the `.venv` active or using `uv run`.

---

## Environment

```bash
uv sync                          # install / refresh all deps
source .venv/bin/activate        # optional: activate venv directly
uv run wiki --help               # top-level CLI help
make status                      # dump info, DB sizes, last run per job
```

---

## Dump Management

```bash
# Download the latest English dump (skips if < 30 days old)
make download

# Force re-download even if fresh
FORCE_DOWNLOAD=1 make download

# Download a specific date
uv run wiki dump download --lang en --date 20260301

# Download a non-English dump
uv run wiki dump download --lang de

# List available dump dates (shows complete vs in-progress)
uv run wiki dump list --lang en

# Show dump file info (block count, page count)
uv run wiki dump info data/dumps/enwiki-20260301-pages-articles-multistream.xml.bz2

# Decompress to raw file for faster repeated extraction (22 GB → ~55 GB, one-time cost)
make preprocess
# or with custom parallelism:
uv run wiki dump preprocess --concurrent 16
```

---

## Databases

Job databases are created automatically on the first run of a job (from each
job's ORM models). There is no separate migration step.

```bash
# Run with a custom output DB — the file is created on demand
uv run wiki extract run jazz --db-url sqlite:///data/databases/jazz_dev.db

# Rebuild the schema from current models by deleting the DB and re-running
rm data/databases/jazz.db
uv run wiki extract run jazz
```

---

## Extraction

```bash
# Run a single job (uses Makefile default: 32 workers)
make extract-jazz
make extract-star_trek

# Run with a specific worker count
uv run wiki extract run jazz --concurrent-blocks 29

# Run all jobs (32 workers each, sequentially)
make extract-all

# Override worker count for all jobs
CONCURRENT=29 make extract-all

# Iterate on a job: only run the first 5 blocks (debug, ~10× faster than a full run)
uv run wiki extract run jazz --limit 5

# Run against a specific dump file
uv run wiki extract run jazz \
    --dump data/dumps/enwiki-20260301-pages-articles-multistream.xml.bz2 \
    --concurrent-blocks 29

# Run with a custom output DB
uv run wiki extract run jazz \
    --db-url sqlite:///data/databases/jazz_test.db \
    --concurrent-blocks 8

# Run with a custom tracking DB
uv run wiki extract run jazz \
    --tracking-db-url sqlite:///data/databases/wiki_dev.db \
    --concurrent-blocks 8

# See all registered jobs
uv run wiki extract list
```

---

## Adding a New Job

```bash
# 1. Create src/wiki_dumps/jobs/my_topic.py implementing ExtractJob
#    (a per-job DeclarativeBase, ORM models, and matches/extract/flush/setup_schema)
#    See docs/prompts/schema-generation.md for the LLM prompt template

# 2. Run it — the DB and its tables are auto-created from the ORM models
uv run wiki extract run my_topic --concurrent-blocks 29
```

---

## Database Inspection

```bash
# Open jazz DB in sqlite3
sqlite3 data/databases/jazz.db

# Quick row counts
sqlite3 data/databases/jazz.db "SELECT COUNT(*) FROM jazz_artists;"
sqlite3 data/databases/jazz.db ".tables"

# Last extraction run per job
sqlite3 data/databases/wiki.db \
  "SELECT schema_name, status, completed_at, pages_processed, pages_matched
   FROM extraction_runs
   WHERE id IN (SELECT MAX(id) FROM extraction_runs GROUP BY schema_name)
   ORDER BY schema_name;"

# Full run history for one job
sqlite3 data/databases/wiki.db \
  "SELECT * FROM extraction_runs WHERE schema_name='jazz' ORDER BY started_at DESC LIMIT 5;"
```

---

## Dev / Quality

```bash
# Run all checks (type check + lint + tests)
make check

uv run pyright                   # type check (expect 0 errors)
uv run ruff check src/           # lint
uv run ruff format src/          # format
uv run pytest tests/ -v          # run tests
uv run pytest tests/test_jobs.py # run a single test file
```

---

## Notebooks

```bash
make notebook                    # launch JupyterLab (uses .venv-nb/)
make setup-nb                    # (re)create Python 3.12 notebook venv
make jupyter-kernel              # re-register Jupyter kernel

# Notebooks live in notebooks/:
#   jazz_eda.ipynb
#   scifi_eda.ipynb
#   scifi_genre_timeline.ipynb
#   scifi_tfidf_clusters.ipynb
#   star_trek_eda.ipynb
```

---

## Common Flags

| Flag | Default | Notes |
|---|---|---|
| `--concurrent-blocks N` | all CPU cores | Parallel worker processes; sweet spot is usually CPU count − 2 |
| `--lang CODE` | `en` | Wikipedia language code for dump download (or `WIKI_LANG`) |
| `--limit N` | none | Stop after N blocks — iterate on a job in seconds, not minutes |
| `--db-url URL` | job default | Override job output database |
| `--tracking-db-url URL` | `wiki.db` | Override `ExtractionRun` tracking database |
| `--dump PATH` | auto-detected | Explicit dump file path |
| `--log-every N` | `500` | Print progress line every N blocks |
