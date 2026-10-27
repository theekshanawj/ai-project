import pytest
from pydantic import ValidationError

from project.models import ApiChange


def test_parses_json() -> None:
    c = ApiChange.model_validate_json(
        '{"endpoint": "/v1/charges", \
    "change_type": "breaking", "effective_date": "2026-12-01"}'
    )
    assert c.effective_date is not None
    assert c.effective_date.year == 2026


def test_rejects_unknown_change_type() -> None:
    with pytest.raises(ValidationError):
        ApiChange.model_validate({"endpoint": "/x", "change_type": "removed"})
