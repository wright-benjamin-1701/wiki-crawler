#!/usr/bin/env bash
# bootstrap.sh — first-time setup for wiki-dumps
#
# What this does:
#   1. Verifies uv is installed (offers to install it)
#   2. Creates the main extraction venv via `uv sync` (Python 3.14)
#   3. Creates data/ directories and .env
#   4. Creates a Python 3.12 notebook venv at .venv-nb/
#   5. Registers it as a Jupyter kernel ("wiki-dumps (Python 3.12)")
#   6. If an NVIDIA GPU is detected, installs RAPIDS (cuDF, cuML) automatically

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

NOTEBOOK_VENV=".venv-nb"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${GREEN}→${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
error()   { echo -e "${RED}✗${NC}  $*" >&2; }
heading() { echo -e "\n${BOLD}$*${NC}"; }

# ── 1. Check for uv ───────────────────────────────────────────────────────────

heading "Checking prerequisites..."

if ! command -v uv &>/dev/null; then
    warn "uv not found. Installing via the official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "uv installation failed. Install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
fi
info "uv $(uv --version)"

# ── 2. Main extraction venv — Python 3.14 ────────────────────────────────────

heading "Installing main extraction venv (Python 3.14)..."

uv sync
info "Main venv ready at .venv/  (used by: uv run wiki ...)"
info "Python: $(uv run python --version)"

# ── 3. Data directories and .env ─────────────────────────────────────────────

heading "Creating data directories..."
mkdir -p data/dumps data/databases
info "data/dumps/ and data/databases/ ready."

if [[ -f .env ]]; then
    info ".env already exists — skipping."
else
    cp .env.example .env
    info "Created .env from .env.example"
    warn "Edit .env if you want to change DATABASE_URL, WIKI_DUMP_DIR, or WIKI_LANG."
fi

# ── 4. Notebook venv — Python 3.12 ───────────────────────────────────────────

heading "Setting up notebook venv (Python 3.12)..."

if [[ -d "$NOTEBOOK_VENV" ]]; then
    info "$NOTEBOOK_VENV/ already exists — skipping creation."
else
    uv venv --python 3.12 "$NOTEBOOK_VENV"
    info "Created $NOTEBOOK_VENV/ with $("$NOTEBOOK_VENV/bin/python" --version)"

    info "Installing notebook deps (pandas, matplotlib, scikit-learn, torch, …)..."
    uv pip install --python "$NOTEBOOK_VENV/bin/python" \
        -e . \
        pandas matplotlib seaborn plotly \
        scikit-learn umap-learn \
        torch torchvision \
        ipykernel jupyter mwparserfromhell
    info "Notebook deps installed."
fi

# ── 5. Jupyter kernel ─────────────────────────────────────────────────────────

heading "Registering Jupyter kernel..."

"$NOTEBOOK_VENV/bin/python" -m ipykernel install \
    --user \
    --name wiki-dumps \
    --display-name "wiki-dumps (Python 3.12)"

info "Kernel 'wiki-dumps (Python 3.12)' registered."

# ── 6. RAPIDS GPU (auto-detected) ────────────────────────────────────────────

if command -v nvidia-smi &>/dev/null; then
    heading "NVIDIA GPU detected — installing RAPIDS into $NOTEBOOK_VENV/..."
    CUDA_VER=$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9][0-9]*\).*/\1/p' | head -1)
    info "CUDA $CUDA_VER  ($(nvidia-smi --query-gpu=name --format=csv,noheader | head -1))"
    uv pip install --python "$NOTEBOOK_VENV/bin/python" \
        "cudf-cu${CUDA_VER}" "cuml-cu${CUDA_VER}" \
        --extra-index-url https://pypi.nvidia.com
    info "RAPIDS installed — scifi_tfidf_clusters.ipynb can use GPU acceleration."
else
    info "No NVIDIA GPU found — skipping RAPIDS. CPU-only mode for all notebooks."
fi

# ── Done ──────────────────────────────────────────────────────────────────────

heading "Bootstrap complete!"
echo ""
echo "  Two environments:"
echo "    .venv/     Python 3.14  extraction CLI   →  uv run wiki ..."
echo "    .venv-nb/  Python 3.12  Jupyter notebooks →  make notebook"
echo ""
echo "  Next steps:"
echo "    make download      download dump + preprocess automatically"
echo "    make extract-all   run all extraction jobs (databases are auto-created)"
echo "    make notebook      open JupyterLab (select kernel: wiki-dumps (Python 3.12))"
echo ""
echo "  Run \`make help\` for all available targets."
echo ""
