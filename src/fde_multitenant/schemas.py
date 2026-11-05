"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .config import KNOWN_METERS


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str


class UsageEventCreate(BaseModel):
    user_id: str = Field(min_length=1)
    meter: str
    quantity: int = Field(ge=0)
    project_id: str | None = None

    def validate_meter(self) -> None:
        if self.meter not in KNOWN_METERS:
            raise ValueError(f"unknown meter: {self.meter!r}")


class UsageEventOut(BaseModel):
    id: int
    tenant_id: str
    user_id: str
    project_id: str | None = None
    meter: str
    quantity: int
