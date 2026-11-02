from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class ApiChange(BaseModel):
    endpoint: str
    change_type: Literal["breaking", "deprecation", "additive"]
    effective_date: date | None = None
    migration_hint: str | None = Field(default=None, max_length=500)


class Release(BaseModel):
    repo: str
    tag_name: str
    published_at: datetime
    name: str | None = None


class StoredRelease(BaseModel):
    release: Release
    stored_at: datetime


# Input Domain

# GitHub "owner/name". Single source of truth: use RepoName wherever a repo is accepted.
RepoName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-zA-Z\d](?:-?[a-zA-Z\d]){0,38}/[a-zA-Z0-9._-]{1,100}$"
    ),
]


class WatchRequest(BaseModel):
    repo: RepoName


class WatchResponse(BaseModel):
    status: str


class PollResult(BaseModel):
    new_releases: int
    failed: int
