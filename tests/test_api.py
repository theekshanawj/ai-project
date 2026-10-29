from fastapi.testclient import TestClient

from project.api import FakeSource, app, get_source

app.dependency_overrides[get_source] = lambda: FakeSource()
client = TestClient(app)


def test_latest_release() -> None:
    r = client.get("/releases/stripe/stripe-python")
    assert r.status_code == 200
    assert r.json()["tag_name"] == "v1.0.0"


def test_batch_returns_one_per_repo() -> None:
    r = client.post("/releases/batch", json={"repos": ["a/b", "c/d", "e/f"]})
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_batch_rejects_empty_list() -> None:
    r = client.post("/releases/batch", json={"repos": []})
    assert r.status_code == 422
