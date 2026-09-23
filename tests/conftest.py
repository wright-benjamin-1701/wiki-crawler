"""Shared test fixtures."""

from __future__ import annotations

import bz2
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wiki_dumps.parse.types import WikiPage

# Minimal MediaWiki XML for two pages
_MINI_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           version="0.11" xml:lang="en">
  <siteinfo>
    <sitename>Wikipedia</sitename>
    <dbname>enwiki</dbname>
  </siteinfo>
  <page>
    <title>Test Article</title>
    <ns>0</ns>
    <id>1</id>
    <revision>
      <id>100</id>
      <timestamp>2024-01-15T12:00:00Z</timestamp>
      <contributor><username>TestUser</username></contributor>
      <text xml:space="preserve">This is a test article.
[[Category:Test Category]]
[[Category:Articles]]
</text>
    </revision>
  </page>
  <page>
    <title>Jazz</title>
    <ns>0</ns>
    <id>2</id>
    <revision>
      <id>200</id>
      <timestamp>2024-02-01T09:30:00Z</timestamp>
      <contributor><username>JazzEditor</username></contributor>
      <text xml:space="preserve">Jazz is a music genre.
[[Category:Jazz music]]
[[Category:American music genres]]
</text>
    </revision>
  </page>
</mediawiki>
"""


@pytest.fixture
def mini_xml_bytes() -> bytes:
    """Raw XML bytes for a mini dump with two pages."""
    return _MINI_XML.encode("utf-8")


@pytest.fixture
def mini_dump_bz2(tmp_path: Path, mini_xml_bytes: bytes) -> Path:
    """A bz2-compressed mini dump file."""
    dump_path = tmp_path / "enwiki-20240101-pages-articles-multistream.xml.bz2"
    with bz2.open(dump_path, "wb") as f:
        f.write(mini_xml_bytes)
    return dump_path


@pytest.fixture
def mini_index_bz2(tmp_path: Path, mini_xml_bytes: bytes) -> Path:
    """A bz2-compressed multistream index corresponding to the mini dump.

    We create a fake index where offset 0 points to both pages.
    """
    index_path = tmp_path / "enwiki-20240101-pages-articles-multistream-index.txt.bz2"
    index_lines = "0:1:Test Article\n0:2:Jazz\n"
    with bz2.open(index_path, "wt", encoding="utf-8") as f:
        f.write(index_lines)
    return index_path


@pytest.fixture
def sample_wiki_page() -> WikiPage:
    """A pre-built WikiPage for unit tests that don't need XML parsing."""
    return WikiPage(
        page_id=42,
        namespace=0,
        title="Miles Davis",
        redirect_to=None,
        categories=("Jazz musicians", "American musicians", "Trumpeters"),
        wikitext="Miles Davis was a jazz trumpeter...",
        revision_id=9999,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        contributor="MusicEditor",
    )


@pytest.fixture
def sqlite_db_url(tmp_path: Path) -> str:
    """A temporary SQLite database URL."""
    return f"sqlite:///{tmp_path / 'test.db'}"
