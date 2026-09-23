"""Protocol defining the interface for extraction jobs."""

from typing import Protocol

from wiki_dumps.parse.types import WikiPage

# Default number of buffered records to accumulate before a job flushes to the
# database. Jobs should import this rather than re-declaring their own constant.
DEFAULT_BATCH_SIZE = 500


class ExtractJob(Protocol):
    """Protocol that all extraction jobs must satisfy.

    Implement this interface to create a new extraction schema.
    See docs/prompts/schema-generation.md for an LLM prompt template.
    """

    name: str
    db_url: str
    default_db_url: str

    def __init__(self, db_url: str) -> None:
        """Construct the job, creating a SQLAlchemy engine for *db_url*."""
        ...

    def matches(self, page: WikiPage) -> bool:
        """Return True if this page should be extracted."""
        ...

    def extract(self, page: WikiPage) -> None:
        """Buffer or write data extracted from *page*.

        Implementations should accumulate records in an internal list and
        flush to the database in batches (see ``flush()``).
        """
        ...

    def flush(self) -> None:
        """Commit any buffered records to the database.

        Called by the runner after every block is processed. Implementations
        must write all pending records and clear the internal buffer.
        """
        ...

    def setup_schema(self) -> None:
        """Create or migrate the schema for this job's database.

        Implementations should call ``<JobBase>.metadata.create_all(self._engine)``.
        """
        ...
