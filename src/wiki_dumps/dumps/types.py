"""Data types for dump files and index entries."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DumpFile:
    """Metadata about a Wikipedia multistream dump file pair."""

    lang: str
    dump_date: date
    articles_url: str
    index_url: str
    articles_path: Path
    index_path: Path

    @property
    def is_downloaded(self) -> bool:
        return self.articles_path.exists() and self.index_path.exists()


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One entry from the multistream index file.

    Each entry maps a byte offset in the bz2 articles file to one
    Wikipedia page ID and title.
    """

    byte_offset: int
    page_id: int
    title: str


@dataclass(frozen=True, slots=True)
class StreamBlock:
    """A contiguous bz2 block covering one or more index entries."""

    start_offset: int
    end_offset: int  # exclusive; -1 means end of file
    entries: tuple[IndexEntry, ...]
