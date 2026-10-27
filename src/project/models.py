from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ApiChange(BaseModel):
    endpoint: str
    change_type: Literal["breaking", "deprecation", "additive"]
    effective_date: date | None = None
    migration_hint: str | None = Field(default=None, max_length=500)
