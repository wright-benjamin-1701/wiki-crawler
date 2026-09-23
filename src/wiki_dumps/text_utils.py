"""Shared text-cleaning utilities for NLP use across notebooks and extraction jobs."""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell  # type: ignore[import-untyped]

_BLANK_LINE_RE = re.compile(r"\n{3,}")
_CATEGORY_RE = re.compile(r"\[\[(?:Category|File|Image|Media):[^\]]*\]\]", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")
_HTML_ENTITY_RE = re.compile(r"&\w+;")
_TEMPLATE_ARTIFACT_RE = re.compile(r"\{\{[^}]{0,200}\}\}")


def strip_wiki_article_text(wikitext: str) -> str:
    """Strip Wikipedia markup from raw wikitext, returning clean prose for NLP.

    Applies mwparserfromhell to remove templates, wikilinks, and other
    MediaWiki constructs, then cleans up residual whitespace and line-noise
    artifacts left by the stripper.

    This is the canonical text-cleaning function for TF-IDF / embedding
    pipelines across all domain notebooks.  Apply domain-specific stopword
    lists on top of the output for best results.
    """
    try:
        wikicode: Any = mwparserfromhell.parse(wikitext)
        stripped: str = str(wikicode.strip_code())
    except Exception:  # noqa: BLE001
        stripped = wikitext

    # Remove leftover template markers the stripper missed
    stripped = _TEMPLATE_ARTIFACT_RE.sub(" ", stripped)
    # Remove Category / File / Image pseudo-links that survive strip_code
    stripped = _CATEGORY_RE.sub(" ", stripped)
    # Remove bare URLs
    stripped = _URL_RE.sub(" ", stripped)
    # Replace HTML entities with a space
    stripped = _HTML_ENTITY_RE.sub(" ", stripped)
    # Drop lines that are too short to be prose (stray chars / punctuation)
    lines = [ln for ln in stripped.splitlines() if len(ln.strip()) > 3]
    stripped = "\n".join(lines)
    # Collapse runs of 3+ blank lines to a single blank line
    stripped = _BLANK_LINE_RE.sub("\n\n", stripped)
    return stripped.strip()
