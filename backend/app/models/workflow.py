from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkflowDefinitionModel(Base):
    __tablename__ = "workflow_definition"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    steps: Mapped[list["WorkflowStepDefModel"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStepDefModel.sort_order",
    )


class WorkflowStepDefModel(Base):
    __tablename__ = "workflow_step_def"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_definition.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="")
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), nullable=False)
    depends_on: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parallel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    on_complete: Mapped[str] = mapped_column(String, nullable=False, default="none")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workflow: Mapped["WorkflowDefinitionModel"] = relationship(back_populates="steps")


class WorkflowRunModel(Base):
    __tablename__ = "workflow_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_definition.id"), nullable=False
    )
    daily_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    steps: Mapped[list["StepRunModel"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )


class StepRunModel(Base):
    __tablename__ = "step_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_run.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow_run: Mapped["WorkflowRunModel"] = relationship(back_populates="steps")
