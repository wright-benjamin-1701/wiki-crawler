"""Minimal extraction job: collect all article-namespace page titles and IDs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from wiki_dumps.db.base import Base
from wiki_dumps.db.session import create_all_tables, get_session, make_engine
from wiki_dumps.extract.base import DEFAULT_BATCH_SIZE
from wiki_dumps.parse.types import WikiPage


class ArticlePage(Base):
    """Stores the title, page ID, and redirect target for every article page."""

    __tablename__ = "article_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int]
    title: Mapped[str]
    redirect_to: Mapped[str | None]
    namespace: Mapped[int]
    revision_id: Mapped[int]
    timestamp: Mapped[datetime]
    contributor: Mapped[str | None]
    category_count: Mapped[int]


class BasePagesJob:
    """Extraction job that collects all article namespace pages."""

    name: str = "base_pages"
    default_db_url: str = "sqlite:///data/databases/wiki.db"

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self._engine = make_engine(db_url)
        self._pending: list[ArticlePage] = []

    def matches(self, page: WikiPage) -> bool:
        return page.namespace == 0

    def extract(self, page: WikiPage) -> None:
        self._pending.append(
            ArticlePage(
                page_id=page.page_id,
                title=page.title,
                redirect_to=page.redirect_to,
                namespace=page.namespace,
                revision_id=page.revision_id,
                timestamp=page.timestamp,
                contributor=page.contributor,
                category_count=len(page.categories),
            )
        )
        if len(self._pending) >= DEFAULT_BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        with get_session(self._engine) as session:
            session.add_all(self._pending)
        self._pending.clear()

    def setup_schema(self) -> None:
        create_all_tables(self._engine)
