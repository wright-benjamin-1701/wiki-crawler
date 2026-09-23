"""Reusable filter helpers for building ExtractJob.matches() methods."""

from __future__ import annotations

import re

from wiki_dumps.parse.types import WikiPage


def has_category(page: WikiPage, category: str, *, case_sensitive: bool = False) -> bool:
    """Return True if *page* belongs to *category* (exact match)."""
    if case_sensitive:
        return category in page.categories
    category_lower = category.lower()
    return any(c.lower() == category_lower for c in page.categories)


def has_category_matching(page: WikiPage, pattern: str | re.Pattern[str]) -> bool:
    """Return True if any of *page*'s categories match *pattern*."""
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    return any(compiled.search(c) for c in page.categories)


def title_matches(page: WikiPage, pattern: str | re.Pattern[str]) -> bool:
    """Return True if *page*'s title matches *pattern*."""
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    return bool(compiled.search(page.title))


def is_article(page: WikiPage) -> bool:
    """Return True if *page* is in the main article namespace (NS=0)."""
    return page.namespace == 0


def is_not_redirect(page: WikiPage) -> bool:
    """Return True if *page* is not a redirect."""
    return page.redirect_to is None


def combine_all(*predicates: object) -> object:
    """Return a predicate that is True only if all *predicates* return True."""
    from collections.abc import Callable

    preds: list[Callable[[WikiPage], bool]] = list(predicates)  # type: ignore[arg-type]

    def _all(page: WikiPage) -> bool:
        return all(p(page) for p in preds)

    return _all


def combine_any(*predicates: object) -> object:
    """Return a predicate that is True if any *predicate* returns True."""
    from collections.abc import Callable

    preds: list[Callable[[WikiPage], bool]] = list(predicates)  # type: ignore[arg-type]

    def _any(page: WikiPage) -> bool:
        return any(p(page) for p in preds)

    return _any
