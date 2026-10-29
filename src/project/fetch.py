import asyncio
import time
from datetime import datetime

import httpx
from pydantic import BaseModel

REPOS = [
    "stripe/stripe-python",
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "encode/httpx",
    "pydantic/pydantic",
]


class Release(BaseModel):
    repo: str
    tag_name: str
    published_at: datetime
    name: str | None = None


async def fetch_latest(client: httpx.AsyncClient, repo: str) -> Release:
    resp = await client.get(f"https://api.github.com/repos/{repo}/releases/latest")
    resp.raise_for_status()
    return Release.model_validate({**resp.json(), "repo": repo})


async def sequential() -> list[Release]:
    async with httpx.AsyncClient(timeout=10) as client:
        return [await fetch_latest(client, r) for r in REPOS]


async def concurrent() -> list[Release]:
    async with httpx.AsyncClient(timeout=10) as client:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch_latest(client, r)) for r in REPOS]
    return [t.result() for t in tasks]


def main() -> None:
    for fn in (sequential, concurrent):
        start = time.perf_counter()
        releases = asyncio.run(fn())
        print(f"{fn.__name__}: {time.perf_counter() - start:.2f}s")
    for r in releases:
        print(f"{r.repo:<40} {r.tag_name:<12} {r.published_at.date()}")


if __name__ == "__main__":
    main()
