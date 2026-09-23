"""ORM model for tracking extraction run metadata."""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from wiki_dumps.db.base import Base


class ExtractionRun(Base):
    """Records metadata for every extraction run.

    Always written regardless of which job schema is in use, providing
    provenance for every generated database.
    """

    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    dump_url: Mapped[str]
    dump_date: Mapped[str]  # "20240101"
    schema_git_commit: Mapped[str]  # git rev-parse HEAD at the time of the run
    schema_name: Mapped[str]  # e.g. "jazz"
    pages_processed: Mapped[int] = mapped_column(default=0)
    pages_matched: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="running")  # running|complete|failed
    error_message: Mapped[str | None]
