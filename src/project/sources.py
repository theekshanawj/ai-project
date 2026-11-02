import asyncio
from datetime import UTC, datetime
from typing import Protocol

import httpx
import structlog

from project.fetch import Release, fetch_latest
from project.settings import Settings

log = structlog.get_logger()


class ReleaseSource(Protocol):
    async def latest(self, repo: str) -> Release: ...


class GitHubSource:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def latest(self, repo: str) -> Release:
        return await fetch_latest(self._client, repo)


class FakeSource:
    async def latest(self, repo: str) -> Release:
        await asyncio.sleep(0.2)
        return Release(
            tag_name="v1.0.0", published_at=datetime.now(UTC), name=repo, repo=repo
        )


def make_source(settings: Settings, client: httpx.AsyncClient) -> ReleaseSource:
    log.info("release source", source=settings.release_source)
    if settings.release_source == "github":
        return GitHubSource(client)
    return FakeSource()
