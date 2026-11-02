import asyncio
from collections import Counter
from typing import Literal

import structlog

from project.models import PollResult
from project.sources import ReleaseSource
from project.store import ReleaseStore

log = structlog.get_logger()


Outcome = Literal["new", "unchanged", "failed"]


async def poll_repo(store: ReleaseStore, source: ReleaseSource, repo: str) -> Outcome:
    """Fetch one repo's latest release and store it."""
    try:
        release = await source.latest(repo)
    except Exception as e:  # one failing repo must not cancel its TaskGroup siblings
        log.warning("poll failed", repo=repo, error=repr(e))
        return "failed"
    return "new" if await store.save_release(repo, release) else "unchanged"


async def poll_once(store: ReleaseStore, source: ReleaseSource) -> PollResult:
    """Poll every watched repo concurrently."""
    repos = await store.list_repos()
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(poll_repo(store, source, repo)) for repo in repos]
    outcomes = Counter(task.result() for task in tasks)
    result = PollResult(new_releases=outcomes["new"], failed=outcomes["failed"])
    log.info("poll finished", repos=len(repos), **result.model_dump())
    return result


async def poll_forever(
    store: ReleaseStore, source: ReleaseSource, interval_seconds: int
) -> None:
    while True:
        try:
            await poll_once(store, source)
        except Exception as e:  # keep the loop alive; a crash here would stop the app
            log.error("poll round failed", error=repr(e))
        await asyncio.sleep(interval_seconds)
