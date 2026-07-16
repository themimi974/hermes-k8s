"""Budget Groups CRUD router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from database import SessionLocal
from models import (
    BudgetGroupCreate,
    BudgetGroupUpdate,
    BudgetGroupInfo,
    BudgetGroupResponse,
    BudgetGroupDeleteResponse,
    BudgetGroupRecord,
    FriendRecord,
)

router = APIRouter(prefix="/api/budget-groups", tags=["budget-groups"])


def _record_to_info(record: BudgetGroupRecord, friend_count: int = 0) -> BudgetGroupInfo:
    return BudgetGroupInfo(
        id=record.id,
        name=record.name,
        description=record.description,
        litellm_team_id=record.litellm_team_id,
        models=record.models or [],
        tpm_limit=record.tpm_limit,
        rpm_limit=record.rpm_limit,
        max_parallel=record.max_parallel,
        max_budget=record.max_budget,
        budget_duration=record.budget_duration,
        friend_count=friend_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[BudgetGroupInfo])
async def list_groups():
    """List all budget groups."""
    db = SessionLocal()
    try:
        records = db.query(BudgetGroupRecord).all()
        result = []
        for r in records:
            count = db.query(FriendRecord).filter(FriendRecord.budget_group_id == r.id).count()
            result.append(_record_to_info(r, count))
        return result
    finally:
        db.close()


@router.get("/{group_id}", response_model=BudgetGroupInfo)
async def get_group(group_id: int):
    """Get a single budget group."""
    db = SessionLocal()
    try:
        record = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")
        count = db.query(FriendRecord).filter(FriendRecord.budget_group_id == group_id).count()
        return _record_to_info(record, count)
    finally:
        db.close()


@router.post("", response_model=BudgetGroupResponse, status_code=201)
async def create_group(body: BudgetGroupCreate):
    """Create a new budget group."""
    db = SessionLocal()
    try:
        existing = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.name == body.name).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Budget group '{body.name}' already exists")

        record = BudgetGroupRecord(
            name=body.name,
            description=body.description,
            models=body.models,
            tpm_limit=body.tpm_limit,
            rpm_limit=body.rpm_limit,
            max_parallel=body.max_parallel,
            max_budget=body.max_budget,
            budget_duration=body.budget_duration,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return BudgetGroupResponse(
            message=f"Budget group '{body.name}' created",
            group=_record_to_info(record),
        )
    finally:
        db.close()


@router.put("/{group_id}", response_model=BudgetGroupResponse)
async def update_group(group_id: int, body: BudgetGroupUpdate):
    """Update a budget group."""
    db = SessionLocal()
    try:
        record = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        update_data = body.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(record, key, value)

        db.commit()
        db.refresh(record)
        count = db.query(FriendRecord).filter(FriendRecord.budget_group_id == group_id).count()
        return BudgetGroupResponse(
            message=f"Budget group '{record.name}' updated",
            group=_record_to_info(record, count),
        )
    finally:
        db.close()


@router.delete("/{group_id}", response_model=BudgetGroupDeleteResponse)
async def delete_group(group_id: int):
    """Delete a budget group. Friends assigned to it will be unassigned."""
    db = SessionLocal()
    try:
        record = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        # Unassign friends from this group
        db.query(FriendRecord).filter(FriendRecord.budget_group_id == group_id).update(
            {"budget_group_id": None}
        )
        db.delete(record)
        db.commit()
        return BudgetGroupDeleteResponse(message=f"Budget group '{record.name}' deleted")
    finally:
        db.close()
