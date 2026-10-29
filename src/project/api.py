import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Protocol

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from project.fetch import Release, fetch_latest
from project.logging_setup import configure_logging

configure_logging()
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=10) as client:
        app.state.client = client
        yield


app = FastAPI(title="Release API", lifespan=lifespan)


def get_source(request: Request) -> ReleaseSource:
    if os.environ.get("RELEASE_SOURCE") == "github":
        log.info("Using real github")
        return GitHubSource(request.app.state.client)
    log.info("Using fake")
    return FakeSource()


Source = Annotated[ReleaseSource, Depends(get_source)]


class BatchRequest(BaseModel):
    repos: list[str] = Field(min_length=1, max_length=20)


@app.get("/releases/{owner}/{repo}")
async def latest_release(owner: str, repo: str, source: Source) -> Release:
    try:
        return await source.latest(f"{owner}/{repo}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"upstream returned {e.response.status_code}"
        ) from e


@app.post("/releases/batch")
async def batch(req: BatchRequest, source: Source) -> list[Release]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(source.latest(r)) for r in req.repos]
    return [t.result() for t in tasks]
