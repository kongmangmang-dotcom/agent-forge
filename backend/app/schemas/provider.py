from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import ProviderType
from app.schemas.common import ORMModel


class ProviderCreate(BaseModel):
    kind: str
    type: ProviderType
    name: str
    endpoint: str = ""
    default_model: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class ProviderUpdate(BaseModel):
    kind: str | None = None
    type: ProviderType | None = None
    name: str | None = None
    endpoint: str | None = None
    default_model: str | None = None
    config: dict[str, Any] | None = None
    capabilities: list[str] | None = None
    status: str | None = None


class ProviderRead(ORMModel):
    id: str
    kind: str
    type: ProviderType
    name: str
    endpoint: str
    default_model: str
    config: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime


class ProviderTestResult(BaseModel):
    ok: bool
    provider_id: str
    message: str
    latency_ms: int | None = None
