"""One-time preprocessing: decompress bz2 multistream → flat raw blocks + binary offset index.

Usage
-----
    uv run wiki dump preprocess

After preprocessing, ``extract run`` automatically detects and uses the raw file,
skipping bz2 decompression entirely on every subsequent run.

File layout
-----------
``<dump>.xml.bz2``           original multistream bz2 (unchanged)
``<dump>.xml.raw``           flat concatenation of all decompressed block bytes (~90 GB)
``<dump>.xml.raw.idx``       binary index: magic(4) + version(1) + uint64 n_blocks,
                             then n_blocks*(offset, length) uint64 pairs
"""

from __future__ import annotations

import bz2
import struct
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from wiki_dumps.dumps.index import parse_index
from wiki_dumps.dumps.types import StreamBlock

console = Console()

# Index binary format:
#   bytes 0-3:  magic b"WRIX"
#   byte  4:    format version (0x01)
#   bytes 5-12: little-endian uint64 n_blocks
#   bytes 13+:  n_blocks * (offset: uint64, length: uint64) pairs
_RAW_IDX_MAGIC = b"WRIX"
_RAW_IDX_VERSION = b"\x01"
_STRUCT_HEADER = struct.Struct("<Q")
_STRUCT_PAIR = struct.Struct("<QQ")


def raw_paths(dump_path: Path) -> tuple[Path, Path]:
    """Return ``(raw_path, idx_path)`` for a given ``.xml.bz2`` dump path."""
    stem = dump_path.stem  # strips .bz2 → "enwiki-...-multistream.xml"
    return dump_path.parent / f"{stem}.raw", dump_path.parent / f"{stem}.raw.idx"


def is_preprocessed(dump_path: Path) -> bool:
    """Return True if both preprocessed files exist for this dump."""
    raw, idx = raw_paths(dump_path)
    return raw.exists() and idx.exists()


def load_raw_index(idx_path: Path) -> list[tuple[int, int]]:
    """Read the binary index and return a list of ``(offset, length)`` per block."""
    data = idx_path.read_bytes()
    preamble_size = len(_RAW_IDX_MAGIC) + len(_RAW_IDX_VERSION)
    if len(data) < preamble_size or data[:4] != _RAW_IDX_MAGIC:
        msg = f"{idx_path.name}: invalid magic — expected b'WRIX', got {data[:4]!r}"
        raise ValueError(msg)
    if data[4:5] != _RAW_IDX_VERSION:
        msg = f"{idx_path.name}: unsupported index version {data[4]:02x} (expected 01)"
        raise ValueError(msg)
    (n,) = _STRUCT_HEADER.unpack_from(data, preamble_size)
    out: list[tuple[int, int]] = []
    pos = preamble_size + _STRUCT_HEADER.size
    for _ in range(n):
        offset, length = _STRUCT_PAIR.unpack_from(data, pos)
        out.append((int(offset), int(length)))
        pos += _STRUCT_PAIR.size
    return out


def _decompress_block(block: StreamBlock, dump_path: Path) -> bytes:
    with dump_path.open("rb") as f:
        f.seek(block.start_offset)
        compressed = (
            f.read() if block.end_offset == -1
            else f.read(block.end_offset - block.start_offset)
        )
    return bz2.decompress(compressed)


def preprocess_dump(
    dump_path: Path,
    index_path: Path,
    *,
    concurrent: int = 8,
) -> tuple[Path, Path]:
    """Decompress all bz2 blocks in parallel and write a raw file + binary offset index.

    The raw file is a flat concatenation of every block's decompressed XML bytes.
    On subsequent ``extract run`` calls the runner seeks directly into this file
    without any bz2 overhead.

    Returns ``(raw_path, idx_path)``.
    """
    blocks = parse_index(index_path)
    n_blocks = len(blocks)
    raw_path, idx_path = raw_paths(dump_path)

    raw_size_gb = dump_path.stat().st_size / 1e9
    console.print(
        f"Preprocessing [bold]{dump_path.name}[/bold] ({raw_size_gb:.1f} GB compressed)\n"
        f"→ [bold]{raw_path.name}[/bold] | {n_blocks:,} blocks | {concurrent} concurrent threads\n"
        f"[yellow]Estimated output size: ~{raw_size_gb * 4.5:.0f}–{raw_size_gb * 5:.0f} GB "
        f"(bz2 ratio ≈ 4–5×)[/yellow]"
    )

    block_offsets: list[tuple[int, int]] = []
    current_offset = 0
    blocks_done = 0
    t_start = time.monotonic()

    # Buffer for results that arrive out of order so we write blocks sequentially
    pending: dict[int, bytes] = {}
    next_to_write = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Decompressing[/bold]"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[cyan]{task.fields[blk_per_s]:.1f}[/cyan] blk/s"),
        TextColumn("[cyan]{task.fields[gb_written]:.2f}[/cyan] GB written"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=2,
    ) as progress:
        task = progress.add_task("decompress", total=n_blocks, blk_per_s=0.0, gb_written=0.0)

        with raw_path.open("wb") as out_f:
            with ThreadPoolExecutor(max_workers=concurrent) as executor:
                # Sliding window: keep at most `concurrent` futures in flight.
                # Submitting all upfront would accumulate every decompressed block
                # (~1.3 MB each × 254k blocks) in Future._result, filling RAM.
                active: dict[Future[bytes], int] = {}
                block_iter = iter(enumerate(blocks))

                def _submit_next() -> None:
                    try:
                        i, block = next(block_iter)
                        active[executor.submit(_decompress_block, block, dump_path)] = i
                    except StopIteration:
                        pass

                # Fill the initial window
                for _ in range(min(concurrent, n_blocks)):
                    _submit_next()

                while active:
                    done, _ = futures_wait(list(active), return_when=FIRST_COMPLETED)
                    for future in done:
                        block_idx = active.pop(future)
                        pending[block_idx] = future.result()
                        _submit_next()  # keep the window full
                    del done  # release completed Future objects and their _result buffers

                    # Flush consecutive blocks to disk in order
                    while next_to_write in pending:
                        data = pending.pop(next_to_write)
                        out_f.write(data)
                        block_offsets.append((current_offset, len(data)))
                        current_offset += len(data)
                        del data  # free immediately after write
                        next_to_write += 1
                        blocks_done += 1

                    wall = time.monotonic() - t_start
                    progress.update(
                        task,
                        completed=blocks_done,
                        blk_per_s=blocks_done / wall if wall > 0 else 0.0,
                        gb_written=current_offset / 1e9,
                    )

    # Write binary index: magic + version + n_blocks + (offset, length) pairs
    idx_data = _RAW_IDX_MAGIC + _RAW_IDX_VERSION + _STRUCT_HEADER.pack(len(block_offsets))
    idx_data += b"".join(_STRUCT_PAIR.pack(off, ln) for off, ln in block_offsets)
    idx_path.write_bytes(idx_data)

    wall_total = time.monotonic() - t_start
    console.print(
        f"[bold green]Done.[/bold green] {n_blocks:,} blocks → "
        f"{current_offset / 1e9:.1f} GB in {wall_total:.0f}s | "
        f"index: {idx_path.name} ({idx_path.stat().st_size / 1e6:.1f} MB)"
    )
    return raw_path, idx_path
