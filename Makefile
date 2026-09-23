# wiki-dumps Makefile
# Run `make help` to see all targets.
#
# Prerequisites: uv must be installed (see https://docs.astral.sh/uv/)
# First time: `make bootstrap` — installs everything and sets up .env

UV           := uv
LANG         := en
CONCURRENT   := 32
NOTEBOOK_VENV := .venv-nb

# All extraction jobs (space-separated)
ALL_JOBS := base_pages jazz scifi \
            literature philosophy mythology \
            classical_music art_history board_games

.PHONY: help bootstrap setup setup-nb download preprocess \
        extract-% extract-all \
        notebook jupyter-kernel \
        check typecheck lint format test \
        status clean

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  wiki-dumps — Wikipedia extraction toolkit"
	@echo ""
	@echo "  First-time setup:"
	@echo "    make bootstrap           Install all deps, .env, data dirs, Jupyter kernel"
	@echo ""
	@echo "  Data pipeline:"
	@echo "    make download            Download latest dump (skips if < 30 days old, auto-preprocesses)"
	@echo "    make preprocess          Re-run preprocessing manually if needed"
	@echo "    make extract-all         Run every extraction job ($(CONCURRENT) workers)"
	@echo "    FORCE_DOWNLOAD=1 make download   Force re-download even if dump is fresh"
	@echo ""
	@echo "  Per-job targets (replace <job> with job name):"
	@echo "    make extract-<job>       e.g. make extract-mythology"
	@echo ""
	@echo "  Available jobs: $(ALL_JOBS)"
	@echo ""
	@echo "  Notebooks (Python 3.12 venv at $(NOTEBOOK_VENV)/):"
	@echo "    make setup-nb            Create Python 3.12 notebook venv + register Jupyter kernel"
	@echo "    make jupyter-kernel      Re-register Jupyter kernel from existing notebook venv"
	@echo "    make notebook            Launch JupyterLab"
	@echo ""
	@echo "  Dev:"
	@echo "    make check               typecheck + lint + tests"
	@echo "    make typecheck           uv run pyright"
	@echo "    make lint                uv run ruff check src/"
	@echo "    make format              uv run ruff format src/"
	@echo "    make test                uv run pytest tests/"
	@echo ""
	@echo "  Inspect:"
	@echo "    make status              Dump info, DB sizes, last extraction run per job"
	@echo ""
	@echo "  Options (override on command line):"
	@echo "    LANG=$(LANG)             Wikipedia language code"
	@echo "    CONCURRENT=$(CONCURRENT)       Parallel worker processes"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────

bootstrap: setup setup-nb
	@echo ""
	@echo "  Bootstrap complete."
	@echo "  Next: make download && make extract-all"
	@echo ""

setup:
	@echo "→ Installing extraction deps (Python 3.14)..."
	$(UV) sync
	@echo "→ Creating data directories..."
	mkdir -p data/dumps data/databases
	@[ -f .env ] && echo "→ .env already exists, skipping." || (cp .env.example .env && echo "→ Created .env from .env.example — edit it if needed.")

# Create a Python 3.12 venv for notebooks and register it as a Jupyter kernel.
setup-nb: jupyter-kernel
	@echo "→ Notebook venv ready at $(NOTEBOOK_VENV)/"

$(NOTEBOOK_VENV):
	@echo "→ Creating Python 3.12 notebook venv at $(NOTEBOOK_VENV)/..."
	$(UV) venv --python 3.12 $(NOTEBOOK_VENV)
	@echo "→ Installing notebook deps into $(NOTEBOOK_VENV)/..."
	$(UV) pip install --python $(NOTEBOOK_VENV)/bin/python \
	    -e . \
	    pandas matplotlib seaborn plotly \
	    scikit-learn umap-learn \
	    torch torchvision \
	    ipykernel jupyter mwparserfromhell

jupyter-kernel: $(NOTEBOOK_VENV)
	@echo "→ Registering 'wiki-dumps (Python 3.12)' Jupyter kernel..."
	$(NOTEBOOK_VENV)/bin/python -m ipykernel install \
	    --user \
	    --name wiki-dumps \
	    --display-name "wiki-dumps (Python 3.12)"
	@echo "→ Kernel registered. In JupyterLab: Kernel > Change Kernel > wiki-dumps (Python 3.12)"

# ── Dump management ───────────────────────────────────────────────────────────

# Downloads the latest dump (skipping if a fresh one exists), then auto-preprocesses.
# Override: FORCE_DOWNLOAD=1 make download
download:
	@recent=$$(find data/dumps -name "*-pages-articles-multistream.xml.bz2" -mtime -30 2>/dev/null | head -1); \
	if [ -n "$$recent" ] && [ "$(FORCE_DOWNLOAD)" != "1" ]; then \
	    echo ""; \
	    echo "  Existing dump is less than 30 days old:"; \
	    ls -lh $$recent; \
	    echo ""; \
	    echo "  Skipping download. Use one of:"; \
	    echo "    make extract-<job>             run a job on the existing dump"; \
	    echo "    FORCE_DOWNLOAD=1 make download  force re-download"; \
	    echo ""; \
	    exit 0; \
	fi; \
	$(UV) run wiki dump download --lang $(LANG); \
	echo ""; \
	echo "→ Auto-preprocessing dump (safe to re-run — skipped if .xml.raw already exists)..."; \
	$(UV) run wiki dump preprocess

# Re-run preprocessing manually (e.g. if you deleted the .xml.raw file).
preprocess:
	$(UV) run wiki dump preprocess

# ── Extraction ────────────────────────────────────────────────────────────────

# Note: job databases are auto-created from each job's ORM models at run time
# (see ExtractJob.setup_schema / <JobBase>.metadata.create_all). There is no
# separate migration step.

# Run a single job: `make extract-mythology`
extract-%:
	$(UV) run wiki extract run $* --concurrent-blocks $(CONCURRENT)

# Run every job sequentially (can take 15–20 min total for a full dump)
extract-all:
	@for job in $(ALL_JOBS); do \
	    echo ""; \
	    echo "══════════════════════════════════════════════════"; \
	    echo "  Extracting: $$job"; \
	    echo "══════════════════════════════════════════════════"; \
	    $(UV) run wiki extract run $$job --concurrent-blocks $(CONCURRENT); \
	done

# ── Notebooks ─────────────────────────────────────────────────────────────────

notebook: $(NOTEBOOK_VENV)
	$(NOTEBOOK_VENV)/bin/jupyter lab notebooks/

# ── Dev ───────────────────────────────────────────────────────────────────────

check: typecheck lint test

typecheck:
	$(UV) run pyright

lint:
	$(UV) run ruff check src/

format:
	$(UV) run ruff format src/

test:
	$(UV) run pytest tests/ -v

# ── Status ────────────────────────────────────────────────────────────────────

status:
	@echo ""
	@echo "  ── Dumps ──────────────────────────────────────────────────────────"
	@dumps=$$(find data/dumps -name "*-pages-articles-multistream.xml.bz2" 2>/dev/null); \
	if [ -z "$$dumps" ]; then \
	    echo "  No dump files found in data/dumps/"; \
	else \
	    for f in $$dumps; do \
	        name=$$(basename $$f); \
	        size=$$(du -sh $$f 2>/dev/null | cut -f1); \
	        age=$$(find $$f -mtime +30 2>/dev/null | wc -l | tr -d ' '); \
	        raw=$${f%.bz2}.raw; \
	        if [ -f "$$raw" ]; then preprocessed="[raw ready]"; else preprocessed="[bz2 only]"; fi; \
	        if [ "$$age" -gt 0 ]; then fresh="[>30d old]"; else fresh="[fresh]"; fi; \
	        echo "  $$size  $$name  $$preprocessed  $$fresh"; \
	    done; \
	fi
	@echo ""
	@echo "  ── Databases ──────────────────────────────────────────────────────"
	@for db in data/databases/*.db; do \
	    [ -f "$$db" ] || continue; \
	    size=$$(du -sh $$db 2>/dev/null | cut -f1); \
	    name=$$(basename $$db); \
	    echo "  $$size  $$name"; \
	done
	@echo ""
	@echo "  ── Last extraction runs (from wiki.db) ────────────────────────────"
	@if [ -f data/databases/wiki.db ]; then \
	    sqlite3 data/databases/wiki.db \
	        "SELECT printf('  %-18s  %-10s  %s  processed=%-9s matched=%s', \
	                schema_name, status, \
	                COALESCE(completed_at, started_at), \
	                pages_processed, pages_matched) \
	         FROM extraction_runs \
	         WHERE id IN (SELECT MAX(id) FROM extraction_runs GROUP BY schema_name) \
	         ORDER BY schema_name;" 2>/dev/null \
	    || echo "  (no runs recorded yet)"; \
	else \
	    echo "  wiki.db not found — it is created automatically on the first extraction run (make extract-all)"; \
	fi
	@echo ""

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	@echo "Removing generated databases..."
	rm -f data/databases/*.db
	@echo "Done. Dump files in data/dumps/ are untouched."
