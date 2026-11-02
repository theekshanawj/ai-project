from bisect import bisect_left
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal, Protocol, assert_never

import aiosqlite
import structlog

from project.models import Release, StoredRelease

log = structlog.get_logger()


class ReleaseStore(Protocol):
    async def add_repo(self, repo: str) -> bool: ...  # False if already watched
    async def remove_repo(self, repo: str) -> bool: ...  # False if it wasn't watched
    async def list_repos(self) -> list[str]: ...
    async def save_release(
        self, repo: str, release: Release
    ) -> bool: ...  # False if this tag is already stored
    async def releases_since(self, since: datetime) -> list[StoredRelease]: ...


class InMemoryStore:
    """Dict/set lookups keep every write O(1); releases are appended in stored_at
    order, so releases_since is a binary search plus a slice."""

    __slots__ = ("_repos", "_release_keys", "_releases")

    def __init__(self) -> None:
        self._repos: dict[
            str, None
        ] = {}  # ordered set: O(1) membership, keeps insertion order
        self._release_keys: set[tuple[str, str]] = (
            set()
        )  # (repo, tag_name) already stored
        self._releases: list[StoredRelease] = []  # always sorted by stored_at

    async def add_repo(self, repo: str) -> bool:
        log.info("Adding repository to watchlist", repo=repo)

        if repo in self._repos:
            return False
        self._repos[repo] = None
        return True

    async def remove_repo(self, repo: str) -> bool:
        # Stored values are None, so pop returns None only if the repo was present: one lookup.
        return self._repos.pop(repo, False) is None

    async def list_repos(self) -> list[str]:
        return list(self._repos)

    async def save_release(self, repo: str, release: Release) -> bool:
        key = (repo, release.tag_name)
        if key in self._release_keys:
            return False
        stored_at = datetime.now(UTC)
        # The wall clock can step backwards (NTP); clamp so the list stays sorted.
        if self._releases and stored_at < self._releases[-1].stored_at:
            stored_at = self._releases[-1].stored_at
        self._release_keys.add(key)
        self._releases.append(StoredRelease(release=release, stored_at=stored_at))
        return True

    async def releases_since(self, since: datetime) -> list[StoredRelease]:
        start = bisect_left(self._releases, since, key=lambda s: s.stored_at)
        return self._releases[start:]


SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (repo TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS releases (
    repo TEXT NOT NULL,
    tag TEXT NOT NULL,
    published_at TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (repo, tag)
);
"""


def _to_text(dt: datetime) -> str:
    # Fixed-width UTC ISO 8601, so comparing the TEXT column sorts chronologically.
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


class SqliteStore:
    """Idempotency comes from the primary keys: INSERT OR IGNORE skips a duplicate,
    and rowcount (1 inserted / 0 ignored) says whether the row is new."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def _write(self, sql: str, params: tuple[str, ...]) -> bool:
        cursor = await self._db.execute(sql, params)
        await self._db.commit()
        return cursor.rowcount == 1

    async def add_repo(self, repo: str) -> bool:
        return await self._write(
            "INSERT OR IGNORE INTO repos (repo) VALUES (?)", (repo,)
        )

    async def remove_repo(self, repo: str) -> bool:
        return await self._write("DELETE FROM repos WHERE repo = ?", (repo,))

    async def list_repos(self) -> list[str]:
        async with self._db.execute("SELECT repo FROM repos ORDER BY rowid") as cur:
            return [row[0] for row in await cur.fetchall()]

    async def save_release(self, repo: str, release: Release) -> bool:
        return await self._write(
            "INSERT OR IGNORE INTO releases (repo, tag, published_at, seen_at)"
            " VALUES (?, ?, ?, ?)",
            (
                repo,
                release.tag_name,
                _to_text(release.published_at),
                _to_text(datetime.now(UTC)),
            ),
        )

    async def releases_since(self, since: datetime) -> list[StoredRelease]:
        async with self._db.execute(
            "SELECT repo, tag, published_at, seen_at FROM releases"
            " WHERE seen_at >= ? ORDER BY seen_at, rowid",
            (_to_text(since),),
        ) as cur:
            rows = await cur.fetchall()
        return [
            StoredRelease(
                release=Release(repo=repo, tag_name=tag, published_at=published_at),
                stored_at=seen_at,
            )
            for repo, tag, published_at, seen_at in rows
        ]


@asynccontextmanager
async def open_store(db_path: str) -> AsyncIterator[SqliteStore]:
    async with aiosqlite.connect(db_path) as db:  # closes the connection on exit
        await db.executescript(SCHEMA)
        await db.commit()
        yield SqliteStore(db)


StoreType = Literal["inmemory", "sqlite"]


@asynccontextmanager
async def get_store(store_type: StoreType, db_path: str) -> AsyncIterator[ReleaseStore]:
    """Pick the store. A context manager because SqliteStore must open and close
    its connection; InMemoryStore just needs no cleanup."""
    if store_type == "inmemory":
        yield InMemoryStore()
    elif store_type == "sqlite":
        async with open_store(db_path) as store:
            yield store
    else:
        assert_never(store_type)  # type checkers: exhaustive; runtime: AssertionError
