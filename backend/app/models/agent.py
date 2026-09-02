from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.provider import ProviderModel


class AgentModel(Base):
    __tablename__ = "agent"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    provider_id: Mapped[str] = mapped_column(String, ForeignKey("provider.id"), nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False, default="")
    role: Mapped[str] = mapped_column(String, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    workspace_path: Mapped[str] = mapped_column(String, nullable=False, default="")
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    provider: Mapped["ProviderModel"] = relationship(back_populates="agents")
