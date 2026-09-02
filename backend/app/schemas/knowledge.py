from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    embedding_model: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    embedding_model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = None


class KnowledgeBaseRead(ORMModel):
    id: str
    name: str
    description: str
    embedding_model: str
    top_k: int
    similarity_threshold: float
    status: str
    document_count: int = 0
    segment_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)
    segment_max_chars: int = Field(default=800, ge=100, le=8000)


class KnowledgeDocumentRead(ORMModel):
    id: str
    knowledge_id: str
    name: str
    content_length: int
    segment_max_chars: int
    status: str
    segment_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentDetail(KnowledgeDocumentRead):
    content: str


class KnowledgeSegmentRead(ORMModel):
    id: str
    knowledge_id: str
    document_id: str
    content: str
    content_length: int
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class KnowledgeSearchHit(BaseModel):
    segment_id: str
    document_id: str
    document_name: str
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeSearchHit]
    embedding_backend: str


class KnowledgeChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class KnowledgeChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    history: list[KnowledgeChatMessage] = Field(default_factory=list)


class KnowledgeChatResponse(BaseModel):
    answer: str
    citations: list[KnowledgeSearchHit]
    chat_backend: str
    embedding_backend: str
