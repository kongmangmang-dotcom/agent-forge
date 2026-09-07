from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DailyTaskModel(Base):
    __tablename__ = "daily_task"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String, nullable=False, default="todo")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requirement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    workflow_definition_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("workflow_definition.id"), nullable=True
    )
    bound_workflow_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    plan_author: Mapped[str | None] = mapped_column(String, nullable=True)
    plan_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    continued_from_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("daily_task.id", ondelete="SET NULL"), nullable=True
    )
    continued_to_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("daily_task.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    plan_items: Mapped[list["TaskPlanItemModel"]] = relationship(
        back_populates="daily_task",
        cascade="all, delete-orphan",
        order_by="TaskPlanItemModel.sort_order",
    )
    notes: Mapped[list["TaskNoteModel"]] = relationship(
        back_populates="daily_task",
        cascade="all, delete-orphan",
        order_by="TaskNoteModel.created_at",
    )
    memories: Mapped[list["TaskMemoryModel"]] = relationship(
        back_populates="daily_task",
        cascade="all, delete-orphan",
        order_by="TaskMemoryModel.created_at",
    )


class TaskPlanItemModel(Base):
    __tablename__ = "task_plan_item"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    daily_task_id: Mapped[str] = mapped_column(
        String, ForeignKey("daily_task.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_time: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="todo")
    agent_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent.id"), nullable=True)
    linked_step_key: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_definition_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("workflow_definition.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    daily_task: Mapped["DailyTaskModel"] = relationship(back_populates="plan_items")


class TaskNoteModel(Base):
    __tablename__ = "task_note"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    daily_task_id: Mapped[str] = mapped_column(
        String, ForeignKey("daily_task.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, default="markdown")
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_path: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    daily_task: Mapped["DailyTaskModel"] = relationship(back_populates="notes")


class TaskMemoryModel(Base):
    __tablename__ = "task_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    daily_task_id: Mapped[str] = mapped_column(
        String, ForeignKey("daily_task.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    daily_task: Mapped["DailyTaskModel"] = relationship(back_populates="memories")