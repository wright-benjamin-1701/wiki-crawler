"""Typed dataclasses for parsed Wikipedia pages."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WikiRevision:
    """A single revision of a Wikipedia page."""

    revision_id: int
    timestamp: datetime
    contributor: str | None
    comment: str | None
    wikitext: str


@dataclass(frozen=True, slots=True)
class WikiPage:
    """A fully parsed Wikipedia page (most-recent revision only)."""

    page_id: int
    namespace: int
    title: str
    redirect_to: str | None
    categories: tuple[str, ...]
    wikitext: str
    revision_id: int
    timestamp: datetime
    contributor: str | None

    @property
    def is_article(self) -> bool:
        """True if this page is in the main article namespace."""
        return self.namespace == 0

    @property
    def is_redirect(self) -> bool:
        return self.redirect_to is not None
