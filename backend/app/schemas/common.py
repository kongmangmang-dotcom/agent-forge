from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class ListResponse(BaseModel, Generic[T]):
    items: list[T]


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    redis: str
    details: dict[str, Any] | None = None
