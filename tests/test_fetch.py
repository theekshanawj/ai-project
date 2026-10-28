from datetime import datetime

from project.fetch import Release


def test_release() -> None:
    now = datetime.now()
    release = Release(repo="stripe/stripe-python", tag_name="v1.0.0", published_at=now)
    assert release.repo == "stripe/stripe-python"
    assert release.tag_name == "v1.0.0"
    assert release.published_at == now