from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding_model: Mapped[str] = mapped_column(String, nullable=False, default="")
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeDocumentModel(Base):
    __tablename__ = "knowledge_document"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        String, ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    segment_max_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    status: Mapped[str] = mapped_column(String, nullable=False, default="indexed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeSegmentModel(Base):
    __tablename__ = "knowledge_segment"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        String, ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
