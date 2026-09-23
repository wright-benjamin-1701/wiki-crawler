# wiki-dumps

Download and process Wikipedia XML dumps in parallel, writing extracted data to
strongly-typed SQLAlchemy-managed SQLite/PostgreSQL databases.

## Quick Start

```bash
# One-command first-time setup (installs deps, creates .env, registers Jupyter kernel)
bash bootstrap.sh

# Download the latest English dump — preprocesses automatically after (~22 GB → 55 GB)
# Skips if an existing dump is < 30 days old; use FORCE_DOWNLOAD=1 make download to override
make download

# Run every extraction job (32 parallel workers). Job databases are auto-created
# from each job's ORM models on first run — no migration step is needed.
make extract-all

# Or run specific jobs:
make extract-literature
make extract-mythology
make extract-philosophy
make extract-classical_music
make extract-art_history
make extract-board_games
```

Run `make help` to see all available targets. For GPU/RAPIDS notebook support, run `bash bootstrap.sh --gpu`.

## Architecture

```
Wikipedia XML dump (.xml.bz2 multistream)
    │
    ▼ dumps/index.py — parse byte-offset index
StreamBlock list (offset → page IDs)
    │
    ▼ extract/runner.py — ProcessPoolExecutor (spawn, no GIL)
       _init_worker() runs once per OS process: builds a fresh
       SQLAlchemy engine so no connection state is shared
       bz2 blocks decompressed in parallel worker processes
    │
    ▼ parse/stream.py — lxml iterparse → WikiPage dataclasses
    │
    ▼ ExtractJob.matches() → ExtractJob.extract() → job.flush()
    │
    ▼ SQLAlchemy ORM → per-job SQLite / PostgreSQL
       each job has its own DeclarativeBase (isolated metadata)
       + ExtractionRun metadata written to tracking DB (wiki.db)
```

### Multistream Format

Wikipedia dumps use a "multistream" format: the `.xml.bz2` file is actually many
concatenated bz2 streams. The companion index file maps byte offsets to page IDs,
enabling parallel random access without reading the entire dump sequentially.

Run `wiki dump preprocess` once to decompress everything to a single `.xml.raw` file —
subsequent extractions skip bz2 decompression entirely, reading via plain `seek + read`.

### Per-Job Databases

Each extraction job writes to its own SQLite database with its own `DeclarativeBase` (so table metadata never leaks across jobs):

| Job | Database |
|---|---|
| `base_pages` | `data/databases/wiki.db` |
| `jazz` | `data/databases/jazz.db` |
| `scifi` | `data/databases/scifi.db` |
| `literature` | `data/databases/literature.db` |
| `philosophy` | `data/databases/philosophy.db` |
| `mythology` | `data/databases/mythology.db` |
| `classical_music` | `data/databases/classical_music.db` |
| `art_history` | `data/databases/art_history.db` |
| `board_games` | `data/databases/board_games.db` |
| `star_trek` | `data/databases/star_trek.db` |

`wiki.db` also stores `extraction_runs` rows for all jobs (provenance tracking).

Tables are created from each job's ORM models on the first run
(`<JobBase>.metadata.create_all` via `setup_schema()`) — there is **no separate
migration step**. Re-run a job to rebuild its schema from the current models.

## What It Produces

After running `wiki extract run jazz --concurrent-blocks 32` against the
English Wikipedia dump (~22 GB), you get a queryable SQLite database in seconds per job:

```
$ uv run wiki extract run jazz --concurrent-blocks 32
Starting jazz | 32 worker process(es) | 254,740 blocks | raw (preprocessed, no bz2)
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 254,740/254,740  41.2 blk/s  180,000 pg/s  0:01:43  | 24,817 matched
Done. 22,891,421 pages in 103.1s (221,935 pg/s) — 24,817 matched

$ sqlite3 data/databases/jazz.db "SELECT title, instruments, birth_year FROM jazz_artists LIMIT 5;"
Miles Davis|trumpet|flugelhorn|1926
John Coltrane|tenor saxophone|soprano saxophone|1926
Bill Evans|piano|1929
Charles Mingus|double bass|piano|1922
Thelonious Monk|piano|1917

$ sqlite3 data/databases/jazz.db "SELECT COUNT(*) FROM jazz_artists; SELECT COUNT(*) FROM jazz_albums;"
18,342
6,491
```

## Built-in Jobs

| Job name | Description | Tables |
|---|---|---|
| `base_pages` | All article-namespace page titles and IDs | `article_pages` |
| `jazz` | Jazz artists, albums, and genres | `jazz_artists`, `jazz_albums`, `jazz_genres` |
| `scifi` | Sci-fi novels, films, and authors | `scifi_novels`, `scifi_films`, `scifi_authors` |
| `literature` | Novels, literary authors/poets, poetry collections | `lit_novels`, `lit_authors`, `lit_poetry` |
| `philosophy` | Philosophers, philosophical works, traditions | `philosophers`, `philosophical_works`, `philosophical_traditions` |
| `mythology` | Deities, legendary creatures, world mythologies | `myth_deities`, `myth_creatures`, `mythologies` |
| `classical_music` | Composers, compositions, operas | `classical_composers`, `classical_works`, `classical_operas` |
| `art_history` | Visual artists, artworks, art movements | `art_artists`, `art_works`, `art_movements` |
| `board_games` | Board games, designers, publishers | `board_games`, `game_designers`, `game_publishers` |
| `star_trek` | Star Trek shows, episodes, movies, books, characters, species, ships | `trek_shows`, `trek_episodes`, `trek_movies`, `trek_books`, `trek_characters`, `trek_species`, `trek_starships` |

## Adding a New Extraction Job

1. Use the LLM prompt in `docs/prompts/schema-generation.md` to generate your job
2. Place the generated file in `src/wiki_dumps/jobs/<name>.py` — it is auto-discovered, no registration needed
3. Run: `uv run wiki extract run <name> --concurrent-blocks 8` — tables are auto-created from the job's ORM models, no migration step

See `docs/outputs/jazz-schema-example.md` and `docs/outputs/scifi-schema-example.md`
for worked examples.

## Notebooks

All notebooks run on a dedicated Python 3.12 venv at `.venv-nb/` (separate from the
Python 3.14 extraction CLI). `make bootstrap` sets this up automatically.

```bash
make notebook   # launches JupyterLab from .venv-nb/
                # select kernel: wiki-dumps (Python 3.12)
```

| Notebook | Description |
|---|---|
| `notebooks/jazz_eda.ipynb` | Jazz DB EDA + wikitext lookup |
| `notebooks/scifi_eda.ipynb` | Sci-fi DB EDA + cross-table analysis |
| `notebooks/scifi_genre_timeline.ipynb` | Genre trends + adaptation lag across decades |
| `notebooks/scifi_tfidf_clusters.ipynb` | TF-IDF → UMAP → KMeans (RAPIDS auto-installed by bootstrap if GPU detected) |

## CLI Reference

```
wiki dump list                       List available dumps on dumps.wikimedia.org
wiki dump download                   Download multistream dump + index
wiki dump info <path>                Show info about a downloaded dump
wiki dump preprocess <path>          Decompress bz2 → raw file for faster extractions

wiki extract list                    List registered extraction jobs
wiki extract run <job>               Run an extraction job
  --dump <path>                      Path to dump file (auto-detected if omitted)
  --concurrent-blocks N              Parallel worker processes (default: all CPU cores)
  --limit N                          Stop after N blocks (iterate on a job in seconds)
  --db-url URL                       Override job's default database URL
  --tracking-db-url URL              Override tracking DB URL (default: wiki.db)
  --log-every N                      Print a stats line every N blocks (default: 500)
```

## Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/databases/wiki.db` | Tracking DB (extraction_runs) |
| `WIKI_DUMP_DIR` | `data/dumps` | Directory for downloaded dumps |
| `WIKI_LANG` | `en` | Wikipedia language edition (default for `--lang` on `wiki dump *` commands) |
| `WIKI_N_JOBS` | `-1` (= all cores) | Default parallel workers for `wiki extract run` (overridden by `--concurrent-blocks`) |

## Development

```bash
uv run pyright          # Type check (strict mode, 0 errors expected)
uv run ruff check src/  # Lint
uv run ruff format src/ # Format
uv run pytest tests/    # Run tests
```

## Requirements

- Python 3.14
- uv (package manager)
- ~25 GB disk space for a full English Wikipedia dump (55 GB preprocessed)
