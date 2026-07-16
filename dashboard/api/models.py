"""Pydantic response models and SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Integer, Float, Text, Boolean, JSON, func, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


# ── Pydantic schemas ──────────────────────────────────────────────


class FriendCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class FriendSnapshot(BaseModel):
    key: str
    size: int
    last_modified: Optional[datetime] = None


class FriendInfo(BaseModel):
    name: str
    namespace: str
    status: str  # "running", "pending", "error", "not-found"
    host: Optional[str] = None
    pods: int = 0
    ready_pods: int = 0
    restarts: int = 0
    pvc_name: str = "friend-data"
    pvc_status: str = "Unknown"
    pvc_size: str = "2Gi"
    ingressroute_host: Optional[str] = None
    budget_group_id: Optional[int] = None
    budget_group_name: Optional[str] = None
    litellm_key: Optional[str] = None


class FriendDetail(FriendInfo):
    username: Optional[str] = None


class CreateResponse(BaseModel):
    message: str
    friend: FriendInfo


class DeleteResponse(BaseModel):
    message: str
    namespace: str


class StateSaveResponse(BaseModel):
    message: str
    snapshot_key: str


class StateRestoreResponse(BaseModel):
    status: str
    snapshot_key: str
    pod: str


class SnapshotListResponse(BaseModel):
    friend: str
    snapshots: list[FriendSnapshot]


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


# ── Budget Group schemas ───────────────────────────────────────────


class BudgetGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    models: list[str] = Field(default_factory=lambda: ["gpt-3.5-turbo"])
    tpm_limit: int = 100000
    rpm_limit: int = 1000
    max_parallel: int = 5
    max_budget: float = 50.0
    budget_duration: str = "30d"


class BudgetGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    models: Optional[list[str]] = None
    tpm_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    max_parallel: Optional[int] = None
    max_budget: Optional[float] = None
    budget_duration: Optional[str] = None


class BudgetGroupInfo(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    litellm_team_id: Optional[str] = None
    models: list[str] = []
    tpm_limit: int = 100000
    rpm_limit: int = 1000
    max_parallel: int = 5
    max_budget: float = 50.0
    budget_duration: str = "30d"
    friend_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BudgetGroupResponse(BaseModel):
    message: str
    group: BudgetGroupInfo


class BudgetGroupDeleteResponse(BaseModel):
    message: str


# ── Usage schemas ──────────────────────────────────────────────────


class UsageSummary(BaseModel):
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    by_model: dict = {}
    by_friend: dict = {}
    period: str = "24h"


# ── SQLAlchemy ORM ─────────────────────────────────────────────────


class FriendRecord(Base):
    """Tracks friend metadata in PostgreSQL."""
    __tablename__ = "friends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text)
    username = Column(String(50), nullable=False)
    namespace = Column(String(60), nullable=False)
    litellm_key = Column(String(128))
    litellm_key_hash = Column(String(128))
    budget_group_id = Column(Integer, ForeignKey("budget_groups.id"))
    litellm_team_id = Column(String(128))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    budget_group = relationship("BudgetGroupRecord", backref="friends")


class BudgetGroupRecord(Base):
    """Budget group configuration."""
    __tablename__ = "budget_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text)
    litellm_team_id = Column(String(128))
    models = Column(JSON, default=list)
    tpm_limit = Column(Integer, default=100000)
    rpm_limit = Column(Integer, default=1000)
    max_parallel = Column(Integer, default=5)
    max_budget = Column(Float, default=50.0)
    budget_duration = Column(String(8), default="30d")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
