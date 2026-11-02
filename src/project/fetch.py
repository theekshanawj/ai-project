import asyncio

import httpx

from project.models import Release


async def fetch_latest(client: httpx.AsyncClient, repo: str) -> Release:
    resp = await client.get(f"https://api.github.com/repos/{repo}/releases/latest")
    resp.raise_for_status()
    return Release.model_validate({**resp.json(), "repo": repo})


async def sequential(repos: list[str]) -> list[Release]:
    async with httpx.AsyncClient(timeout=10) as client:
        return [await fetch_latest(client, r) for r in repos]


async def concurrent(repos: list[str]) -> list[Release]:
    async with httpx.AsyncClient(timeout=10) as client:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch_latest(client, r)) for r in repos]
    return [t.result() for t in tasks]
