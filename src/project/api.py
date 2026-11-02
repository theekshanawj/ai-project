import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, HTTPException, status
from pydantic import AwareDatetime

from project.config.logging_setup import configure_logging
from project.models import (
    PollResult,
    RepoName,
    StoredRelease,
    WatchRequest,
    WatchResponse,
)
from project.poller import poll_forever, poll_once
from project.settings import Settings
from project.sources import make_source
from project.store import get_store

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    headers = {}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"

    # Exits run in reverse: the poller stops first, then the client, then the DB.
    async with (
        get_store(settings.store_type, settings.db_path) as store,
        httpx.AsyncClient(timeout=10, headers=headers) as client,
        asyncio.TaskGroup() as tg,
    ):
        app.state.store = store
        app.state.source = make_source(settings, client)
        poller = tg.create_task(
            poll_forever(
                app.state.store, app.state.source, settings.poll_interval_seconds
            )
        )
        yield
        poller.cancel()  # otherwise the TaskGroup waits forever on shutdown


app = FastAPI(title="Release API", lifespan=lifespan)


@app.post("/watchlist", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(req: WatchRequest) -> WatchResponse:
    try:
        added = await app.state.store.add_repo(req.repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not added:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Repository already watched"
        )
    return WatchResponse(status="success")


@app.get("/watchlist")
async def get_watchlist() -> list[str]:
    return await app.state.store.list_repos()


# {repo:path} so the "/" in "owner/name" is captured instead of ending the route.
@app.delete("/watchlist/{repo:path}")
async def remove_from_watchlist(repo: RepoName) -> WatchResponse:
    removed = await app.state.store.remove_repo(repo)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )
    return WatchResponse(status="success")


@app.get("/releases")
async def get_releases(since: AwareDatetime) -> list[StoredRelease]:
    releases = await app.state.store.releases_since(since)
    return releases[::-1]  # store keeps oldest first; API returns newest first


@app.post("/poll")
async def poll() -> PollResult:
    """Poll all watched repos now, without waiting for the next scheduled round."""
    return await poll_once(app.state.store, app.state.source)
