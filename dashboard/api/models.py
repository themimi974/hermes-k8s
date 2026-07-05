"""Pydantic response models and SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, func

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


# ── SQLAlchemy ORM ─────────────────────────────────────────────────

class FriendRecord(Base):
    """Tracks friend metadata in PostgreSQL."""
    __tablename__ = "friends"

    name = Column(String(50), primary_key=True)
    username = Column(String(50), nullable=False)
    namespace = Column(String(60), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
