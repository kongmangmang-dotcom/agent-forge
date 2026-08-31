from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProviderModel(Base):
    __tablename__ = "provider"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False, default="")
    default_model: Mapped[str] = mapped_column(String, nullable=False, default="")
    config_encrypted: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="disconnected")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agents: Mapped[list["AgentModel"]] = relationship(back_populates="provider")
