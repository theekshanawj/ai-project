from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from project.store import StoreType

# Project root (src/project/settings.py -> ../../), so .env is found no matter
# which directory the app is started from.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # Precedence: real environment variables > .env file > defaults below.
    model_config = SettingsConfigDict(
        env_prefix="RW_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",  # .env may hold keys for other tools
        env_ignore_empty=True,  # "RW_GITHUB_TOKEN=" means unset, not ""
    )

    release_source: Literal["fake", "github"] = "fake"
    store_type: StoreType = "sqlite"
    poll_interval_seconds: int = Field(default=900, ge=10)
    db_path: str = "releases.db"
    github_token: SecretStr | None = None
