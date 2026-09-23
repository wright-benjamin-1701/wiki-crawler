"""Streaming XML parser that yields WikiPage objects from a bz2 dump block."""

from __future__ import annotations

import bz2
import io
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

from wiki_dumps.dumps.types import StreamBlock
from wiki_dumps.parse.types import WikiPage

_NS = "http://www.mediawiki.org/xml/export-0.11/"
_CATEGORY_RE = re.compile(r"\[\[Category:([^\]|]+)", re.IGNORECASE)


def _tag(local: str) -> str:
    return f"{{{_NS}}}{local}"


def _find_text(elem: etree._Element, local: str) -> str | None:  # type: ignore[name-defined]
    child = elem.find(_tag(local))
    return child.text if child is not None else None


def _parse_timestamp(ts: str | None) -> datetime:
    if not ts:
        return datetime(1970, 1, 1, tzinfo=UTC)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _extract_categories(wikitext: str) -> tuple[str, ...]:
    return tuple(m.strip() for m in _CATEGORY_RE.findall(wikitext))


def _parse_page(page_elem: etree._Element) -> WikiPage | None:  # type: ignore[name-defined]
    """Parse a single <page> element into a WikiPage, or return None on error."""
    ns_text = _find_text(page_elem, "ns")
    id_text = _find_text(page_elem, "id")
    title_text = _find_text(page_elem, "title")
    if ns_text is None or id_text is None or title_text is None:
        return None

    namespace = int(ns_text)
    page_id = int(id_text)
    title = title_text

    redirect_elem = page_elem.find(_tag("redirect"))
    redirect_to: str | None = None
    if redirect_elem is not None:
        redirect_to = redirect_elem.get("title")

    # Use the most recent (last) revision
    revision = None
    for rev_elem in page_elem.findall(_tag("revision")):
        revision = rev_elem

    if revision is None:
        return None

    rev_id_text = _find_text(revision, "id")
    rev_id = int(rev_id_text) if rev_id_text else 0
    timestamp = _parse_timestamp(_find_text(revision, "timestamp"))

    contributor_elem = revision.find(_tag("contributor"))
    contributor: str | None = None
    if contributor_elem is not None:
        contributor = _find_text(contributor_elem, "username") or _find_text(
            contributor_elem, "ip"
        )

    text_elem = revision.find(_tag("text"))
    wikitext = (text_elem.text or "") if text_elem is not None else ""

    return WikiPage(
        page_id=page_id,
        namespace=namespace,
        title=title,
        redirect_to=redirect_to,
        categories=_extract_categories(wikitext),
        wikitext=wikitext,
        revision_id=rev_id,
        timestamp=timestamp,
        contributor=contributor,
    )


def _read_block_bytes(articles_path: Path, block: StreamBlock) -> bytes:
    with articles_path.open("rb") as f:
        f.seek(block.start_offset)
        return f.read() if block.end_offset == -1 else f.read(block.end_offset - block.start_offset)


_ROOT_OPEN = f'<root xmlns="{_NS}">'.encode()


def _iter_pages_from_xml(xml_bytes: bytes) -> Iterator[WikiPage]:
    """Parse WikiPage objects from raw (uncompressed) XML block bytes."""
    # Strip XML declaration if present — it cannot appear inside a <root> wrapper.
    if xml_bytes.lstrip().startswith(b"<?xml"):
        xml_bytes = xml_bytes[xml_bytes.index(b"?>") + 2 :]
    # Inject the default namespace on <root> so that blocks 1..N, which contain
    # bare <page> elements with no surrounding <mediawiki> declaration, still match
    # the qualified tag filter {http://...}page used by iterparse.
    wrapped = _ROOT_OPEN + xml_bytes + b"</root>"
    context = etree.iterparse(  # noqa: S320 — local data, not user input
        io.BytesIO(wrapped),
        events=("end",),
        tag=_tag("page"),
    )
    for _, page_elem in context:
        page = _parse_page(page_elem)
        if page is not None:
            yield page
        page_elem.clear()


def iter_pages_from_bytes(compressed: bytes) -> Iterator[WikiPage]:
    """Parse a single bz2 block given its raw compressed bytes."""
    yield from _iter_pages_from_xml(bz2.decompress(compressed))


def iter_pages_from_xml_bytes(xml_bytes: bytes) -> Iterator[WikiPage]:
    """Parse a single block given its raw *uncompressed* XML bytes.

    Use this after preprocessing (``wiki dump preprocess``) to skip bz2 overhead.
    """
    yield from _iter_pages_from_xml(xml_bytes)


def iter_pages_from_block(
    articles_path: Path, block: StreamBlock
) -> Iterator[WikiPage]:
    """Yield WikiPage objects from a single bz2 stream block."""
    compressed = _read_block_bytes(articles_path, block)
    yield from iter_pages_from_bytes(compressed)


def iter_pages_from_dump(articles_path: Path) -> Iterator[WikiPage]:
    """Yield WikiPage objects by streaming the entire dump sequentially.

    Use this for small dumps or when you don't need parallel access.
    For parallel access, use iter_pages_from_block with Dask.
    """
    with bz2.open(articles_path, "rb") as f:
        context = etree.iterparse(
            io.BytesIO(f.read()),
            events=("end",),
            tag=_tag("page"),
        )
        for _, page_elem in context:
            page = _parse_page(page_elem)
            if page is not None:
                yield page
            page_elem.clear()
