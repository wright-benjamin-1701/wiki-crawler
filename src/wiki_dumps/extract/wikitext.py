"""Shared wikitext / infobox extraction helpers.

Every extraction job parses Wikimedia ``{{Infobox ...}}`` templates the same way:
pull a scalar field, strip markup from a scalar, normalise a list into a
pipe-separated string, find the first sentence, or read a year out of a value.

This module is the single source of truth for those primitives so that new jobs
don't re-copy them (the root cause of a recurring "fixed in one job, forgot the
other" bug class). Import from here:

    from wiki_dumps.extract.wikitext import (
        clean_list_field,
        extract_year,
        first_sentence,
        infobox_value,
        strip_wikitext,
    )

Notes
-----
* ``extract_year`` matches 1000–2029 inclusive. The 1000+ lower bound is the
  union of the previously per-job variants (jazz ``1[89]``, classical_music
  ``1[3-9]``, literature ``1[0-9]``) — a strict superset that only ever adds a
  valid year, never drops one.
* ``clean_list_field``'s plain-text split is ``[, \\n*•]+`` — the broadest variant
  used by 8 of 9 existing jobs. It is also a strict superset of jazz's
  ``[, \\n]+`` (it additionally splits on ``*`` and ``•``, which is what
  MediaWiki list markup produces).
"""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell  # type: ignore[import-untyped]

# 1000–2029 inclusive, word-bounded. Strict superset of every per-job variant.
YEAR_RE = re.compile(r"\b(1[0-9]\d{2}|20[012]\d)\b")
# Common MediaWiki "list-as-template" family.
LIST_TEMPLATES: frozenset[str] = frozenset({"hlist", "flatlist", "plainlist", "unbulleted list", "ubl"})
# Fallback split for bare-text list values — commas, newlines, bullet chars.
_LIST_SPLIT_RE = re.compile(r"[,\n*•]+")


def infobox_value(wikicode: Any, key: str) -> str | None:
    """Return the raw string value of *key* from the first matching template.

    Returns ``None`` when no template carries ``key`` or the value strips to
    empty. *wikicode* is the parsed ``WikiNode`` for the page.
    """
    for template in wikicode.filter_templates():
        if template.has(key):
            return str(template.get(key).value).strip() or None
    return None


def strip_wikitext(raw: str | None) -> str | None:
    """Strip wikitext markup from a scalar value, returning plain prose.

    ``None`` / empty input short-circuits to ``None`` (no unnecessary parse).
    """
    if not raw:
        return None
    result = mwparserfromhell.parse(raw).strip_code().strip()
    return result or None


def clean_list_field(raw: str | None) -> str | None:
    """Normalise a raw list value to a plain pipe-separated string.

    Understands ``{{hlist|a|b}}`` and friends (see ``LIST_TEMPLATES``) and,
    as a fallback, splits on commas / newlines / bullet characters.
    """
    if not raw:
        return None
    wikicode: Any = mwparserfromhell.parse(raw)
    items: list[str] = []
    for tmpl in wikicode.filter_templates():
        if str(tmpl.name).strip().lower() in LIST_TEMPLATES:
            for param in tmpl.params:
                if not param.showkey:  # positional params are the list items
                    item = mwparserfromhell.parse(str(param.value)).strip_code().strip()
                    if item:
                        items.append(item)
    if not items:
        plain = wikicode.strip_code().strip()
        items = [i.strip() for i in _LIST_SPLIT_RE.split(plain) if i.strip()]
    return "|".join(items) or None


def first_sentence(wikicode: Any) -> str | None:
    """Return the first sentence (up to the first period) of stripped prose."""
    plain = wikicode.strip_code().strip()
    sentence = plain.split(".")[0].strip() if plain else None
    return sentence or None


def extract_year(text: str | None) -> int | None:
    """Return the first YYYY year found in *text*, or ``None``."""
    if not text:
        return None
    m = YEAR_RE.search(text)
    return int(m.group()) if m else None
