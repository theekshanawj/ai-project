import asyncio
import random
import time

import httpx
from pydantic import BaseModel, Field

# JSONPlaceholder serves posts with ids 1..100
POST_IDS = random.sample(range(1, 101), 5)

sem = asyncio.Semaphore(2)

class Post(BaseModel):
    id: int
    user_id: int = Field(alias="userId")
    title: str
    body: str

async def fetch_post(client: httpx.AsyncClient, post_id: int) -> Post:
    async with sem:
        resp = await client.get(f"https://jsonplaceholder.typicode.com/posts/{post_id}")
        resp.raise_for_status()
        return Post.model_validate(resp.json())

async def sequential() -> list[Post]:
    async with httpx.AsyncClient(timeout=10) as client:
        return [await fetch_post(client, i) for i in POST_IDS]

async def concurrent() -> list[Post]:
    async with httpx.AsyncClient(timeout=10) as client:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch_post(client, i)) for i in POST_IDS]
    return [t.result() for t in tasks]

def main() -> None:
    for fn in (sequential, concurrent):
        start = time.perf_counter()
        posts = asyncio.run(fn())
        print(f"{fn.__name__}: {time.perf_counter() - start:.2f}s")
    for p in posts:
        print(f"{p.id:<4} user={p.user_id:<3} {p.title}")

if __name__ == "__main__":
    main()
