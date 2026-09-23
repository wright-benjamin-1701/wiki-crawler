"""Application settings loaded from environment variables / .env file."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WIKI_",
        extra="ignore",
    )

    # Override prefix for DATABASE_URL (no WIKI_ prefix)
    database_url: str = "sqlite:///data/databases/wiki.db"
    dump_dir: Path = Path("data/dumps")
    lang: str = "en"
    n_jobs: int = -1  # parallel workers for notebook operations (-1 = all cores)

    @field_validator("dump_dir", mode="before")
    @classmethod
    def coerce_path(cls, v: object) -> Path:
        return Path(str(v))

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_db_url(cls, v: object) -> str:
        s = str(v)
        if not (s.startswith("sqlite") or s.startswith("postgresql")):
            msg = f"DATABASE_URL must be sqlite or postgresql, got: {s!r}"
            raise ValueError(msg)
        return s


class _SettingsConfig(Settings):
    """Separate model that reads DATABASE_URL without the WIKI_ prefix."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


def get_settings() -> Settings:
    """Return application settings, reading DATABASE_URL without prefix."""
    return _SettingsConfig()  # type: ignore[return-value]
