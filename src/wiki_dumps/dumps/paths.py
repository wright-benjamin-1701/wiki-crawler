"""Shared dump-file path helpers.

Wikipedia article dumps are always paired with a sibling index file whose name
differs only in the ``-index.txt`` segment. This module is the single source of
truth for deriving one path from the other, so the CLI never re-implements the
string swap.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wiki_dumps.dumps.types import DumpFile

# Canonical glob for the multistream articles dump.
ARTICLES_GLOB = "*-pages-articles-multistream.xml.bz2"
# The exact "-index.txt" segment that distinguishes the index file from the articles file.
_INDEX_SEGMENT = "-index.txt"


def index_path_for(articles_path: Path) -> Path:
    """Return the paired ``-index.txt`` path for a multistream articles dump.

    ``enwiki-...-pages-articles-multistream.xml.bz2``
      → ``enwiki-...-pages-articles-multistream-index.txt.bz2``
    """
    return articles_path.with_name(articles_path.name.replace("-multistream.xml", "-multistream-index.txt"))


def articles_path_for(dump: DumpFile | Path) -> Path:
    """Return the articles path (identity for ``Path``; the articles path for ``DumpFile``)."""
    return dump if isinstance(dump, Path) else dump.articles_path


def find_dump(directory: Path) -> Path | None:
    """Return the most recent multistream articles dump in *directory*, or None."""
    candidates = sorted(directory.glob(ARTICLES_GLOB))
    return candidates[-1] if candidates else None
