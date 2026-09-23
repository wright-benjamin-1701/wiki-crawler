# Contributing

## Setup

```bash
git clone https://github.com/benwright/wiki-dumps
cd wiki-dumps
bash bootstrap.sh
```

## Development workflow

```bash
uv run pyright          # type check (expect 0 errors)
uv run ruff check src/  # lint
uv run ruff format src/ # format
uv run pytest tests/    # tests
```

All four must pass before opening a PR. CI will enforce this.

## Adding an extraction job

See the [Adding a New Extraction Job](README.md#adding-a-new-extraction-job) section of the README and the LLM prompt template at `docs/prompts/schema-generation.md`.

Jobs are auto-discovered — drop a file implementing `ExtractJob` into `src/wiki_dumps/jobs/` and it will appear in `wiki extract list`.

## Pull requests

- Keep PRs focused — one feature or fix per PR
- Add or update tests for any changed behaviour
- New jobs should include an `ExtractionRun`-compatible implementation and a brief entry in the README jobs table
- Commit messages: imperative mood, present tense (`Add mythology job`, not `Added mythology job`)

## Reporting issues

Open an issue on GitHub. Include:
- OS and Python version
- The command you ran
- Full error output / traceback
