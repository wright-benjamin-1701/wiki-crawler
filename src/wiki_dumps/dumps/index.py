"""Parse the multistream index file into StreamBlocks for parallel access."""

from __future__ import annotations

import bz2
from pathlib import Path

from wiki_dumps.dumps.types import IndexEntry, StreamBlock


def parse_index(index_path: Path) -> list[StreamBlock]:
    """Parse a multistream index .txt.bz2 file into a list of StreamBlocks.

    The index format is: ``<byte_offset>:<page_id>:<title>`` — one line per page.
    All entries with the same byte_offset belong to the same bz2 block.
    """
    entries_by_offset: dict[int, list[IndexEntry]] = {}

    with bz2.open(index_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            # offset and page_id are the first two colon-separated fields;
            # title may contain colons
            first_colon = line.index(":")
            second_colon = line.index(":", first_colon + 1)
            offset = int(line[:first_colon])
            page_id = int(line[first_colon + 1 : second_colon])
            title = line[second_colon + 1 :]
            entry = IndexEntry(byte_offset=offset, page_id=page_id, title=title)
            entries_by_offset.setdefault(offset, []).append(entry)

    sorted_offsets = sorted(entries_by_offset)
    blocks: list[StreamBlock] = []
    for i, offset in enumerate(sorted_offsets):
        end = sorted_offsets[i + 1] if i + 1 < len(sorted_offsets) else -1
        blocks.append(
            StreamBlock(
                start_offset=offset,
                end_offset=end,
                entries=tuple(entries_by_offset[offset]),
            )
        )
    return blocks
