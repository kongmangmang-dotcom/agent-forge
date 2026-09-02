from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RoleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    system_prompt: str = ""
    default_provider_kind: str = ""
    sort_order: int = 0


class RoleUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    system_prompt: str | None = None
    default_provider_kind: str | None = None
    sort_order: int | None = None


class RoleRead(ORMModel):
    id: str
    code: str
    name: str
    description: str
    system_prompt: str
    default_provider_kind: str
    sort_order: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
