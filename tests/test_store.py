from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project.models import Release
from project.store import (
    InMemoryStore,
    ReleaseStore,
    SqliteStore,
    StoreType,
    get_store,
    open_store,
)


def make_release(repo: str = "octo/demo", tag: str = "v1.0.0") -> Release:
    return Release(
        repo=repo, tag_name=tag, published_at=datetime(2026, 1, 1, tzinfo=UTC)
    )


@pytest.fixture(params=["memory", "sqlite"])
async def store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[ReleaseStore]:
    """Every contract test below runs once per store implementation."""
    if request.param == "memory":
        yield InMemoryStore()
    else:
        async with open_store(str(tmp_path / "test.db")) as sqlite_store:
            yield sqlite_store


def test_satisfies_protocol() -> None:
    store: ReleaseStore = InMemoryStore()
    assert store is not None
    _: type[ReleaseStore] = SqliteStore  # type-checked by mypy


async def test_add_repo_is_idempotent_and_keeps_order(store: ReleaseStore) -> None:
    assert await store.add_repo("octo/b") is True
    assert await store.add_repo("octo/a") is True
    assert await store.add_repo("octo/b") is False
    assert await store.list_repos() == ["octo/b", "octo/a"]


async def test_remove_repo(store: ReleaseStore) -> None:
    await store.add_repo("octo/a")
    assert await store.remove_repo("octo/a") is True
    assert await store.remove_repo("octo/a") is False
    assert await store.list_repos() == []


async def test_list_repos_returns_a_copy(store: ReleaseStore) -> None:
    await store.add_repo("octo/a")
    (await store.list_repos()).append("octo/evil")
    assert await store.list_repos() == ["octo/a"]


async def test_instances_do_not_share_state() -> None:
    first, second = InMemoryStore(), InMemoryStore()
    await first.add_repo("octo/a")
    await first.save_release("octo/a", make_release("octo/a"))
    assert await second.list_repos() == []
    assert await second.releases_since(datetime.min.replace(tzinfo=UTC)) == []


async def test_save_release_dedups_on_repo_and_tag(store: ReleaseStore) -> None:
    assert await store.save_release("octo/a", make_release("octo/a", "v1")) is True
    assert await store.save_release("octo/a", make_release("octo/a", "v1")) is False
    assert await store.save_release("octo/a", make_release("octo/a", "v2")) is True
    assert await store.save_release("octo/b", make_release("octo/b", "v1")) is True


T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    """Stands in for the datetime class inside project.store; now() pops scripted times."""

    def __init__(self, *times: datetime) -> None:
        self._times = list(times)

    def now(self, tz=None) -> datetime:
        return self._times.pop(0)


def tags(stored) -> list[str]:
    return [s.release.tag_name for s in stored]


async def test_releases_since_filters_by_stored_at(
    store: ReleaseStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    monkeypatch.setattr("project.store.datetime", FakeClock(*times))
    for tag in ("v1", "v2", "v3"):
        await store.save_release("octo/a", make_release("octo/a", tag))

    assert tags(await store.releases_since(T0 - timedelta(days=1))) == [
        "v1",
        "v2",
        "v3",
    ]
    assert tags(await store.releases_since(T0 + timedelta(seconds=30))) == ["v2", "v3"]
    assert tags(await store.releases_since(T0 + timedelta(minutes=1))) == [
        "v2",
        "v3",
    ]  # inclusive
    assert await store.releases_since(T0 + timedelta(days=1)) == []


async def test_clock_going_backwards_keeps_order(monkeypatch) -> None:
    monkeypatch.setattr(
        "project.store.datetime", FakeClock(T0, T0 - timedelta(minutes=5))
    )
    store = InMemoryStore()
    await store.save_release("octo/a", make_release("octo/a", "v1"))
    await store.save_release("octo/a", make_release("octo/a", "v2"))

    stored = await store.releases_since(T0)
    assert tags(stored) == ["v1", "v2"]
    assert stored[1].stored_at == T0


# SQLite-only


async def test_sqlite_persists_across_reopen(tmp_path: Path) -> None:
    db = str(tmp_path / "test.db")
    async with open_store(db) as first:
        await first.add_repo("octo/a")
        await first.save_release("octo/a", make_release("octo/a", "v1"))
    async with open_store(db) as second:
        assert await second.list_repos() == ["octo/a"]
        duplicate = make_release("octo/a", "v1")
        assert await second.save_release("octo/a", duplicate) is False


async def test_sqlite_round_trips_release_fields(tmp_path: Path) -> None:
    published = datetime(2026, 3, 4, 5, 6, 7, 890, tzinfo=UTC)
    async with open_store(str(tmp_path / "test.db")) as store:
        await store.save_release(
            "octo/a",
            Release(repo="octo/a", tag_name="v9", published_at=published),
        )
        [stored] = await store.releases_since(T0 - timedelta(days=3650))
    assert stored.release.repo == "octo/a"
    assert stored.release.tag_name == "v9"
    assert stored.release.published_at == published
    assert stored.stored_at.tzinfo is not None


# Store selection


@pytest.mark.parametrize(
    ("store_type", "expected"), [("inmemory", InMemoryStore), ("sqlite", SqliteStore)]
)
async def test_get_store_picks_implementation(
    store_type: StoreType, expected: type, tmp_path: Path
) -> None:
    async with get_store(store_type, str(tmp_path / "test.db")) as store:
        assert isinstance(store, expected)


async def test_get_store_rejects_unknown_type(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="redis"):
        async with get_store("redis", str(tmp_path / "test.db")):  # type: ignore[arg-type]
            pass
