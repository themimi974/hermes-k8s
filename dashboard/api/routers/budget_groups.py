"""Budget Groups CRUD router — uses junction table for friend assignments."""
from __future__ import annotations

import logging

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
from services import litellm_client, k8s
from services.merge import merge_groups

logger = logging.getLogger(__name__)
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


def _get_friend_count_for_group(db, group_id: int) -> int:
    """Count friends assigned to a group via junction table."""
    from models import friend_budget_groups
    return db.query(friend_budget_groups).filter(
        friend_budget_groups.c.group_id == group_id
    ).count()


def _get_friends_in_group(db, group_id: int) -> list[FriendRecord]:
    """Get all friends assigned to a group via junction table."""
    from models import friend_budget_groups
    friend_ids = db.query(friend_budget_groups.c.friend_id).filter(
        friend_budget_groups.c.group_id == group_id
    ).subquery()
    return db.query(FriendRecord).filter(FriendRecord.id.in_(friend_ids)).all()


async def _propagate_to_friends(db, group: BudgetGroupRecord):
    """Re-merge and update LiteLLM keys for all friends in this group.

    Each friend may belong to multiple groups, so we recompute their
    merged settings from ALL their assigned groups (not just this one).
    Also updates hermes config ConfigMap + restarts pods.
    """
    friends = _get_friends_in_group(db, group.id)
    propagated = 0
    for friend in friends:
        if friend.litellm_key:
            try:
                merged = merge_groups(friend.groups)
                await litellm_client.update_virtual_key(
                    token=friend.litellm_key,
                    models=merged["models"],
                    tpm_limit=merged["tpm_limit"],
                    rpm_limit=merged["rpm_limit"],
                    max_budget=merged["max_budget"],
                    budget_duration=merged["budget_duration"],
                )
                # Update hermes config + restart pod
                ns = f"friend-{friend.name}"
                default_model = merged["models"][0] if merged["models"] else "gpt-3.5-turbo"
                k8s.update_hermes_configmap(ns, default_model, friend.litellm_key)
                k8s.restart_deployment(ns)
                propagated += 1
            except Exception as e:
                logger.warning(f"Failed to update key/config for friend '{friend.name}': {e}")
    return propagated, len(friends)


@router.get("", response_model=list[BudgetGroupInfo])
async def list_groups():
    """List all budget groups."""
    db = SessionLocal()
    try:
        records = db.query(BudgetGroupRecord).all()
        return [
            _record_to_info(r, _get_friend_count_for_group(db, r.id))
            for r in records
        ]
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
        return _record_to_info(record, _get_friend_count_for_group(db, group_id))
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
    """Update a budget group. Propagates merged settings to all assigned friends."""
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

        # Propagate to all friends who have this group (re-merge from all their groups)
        propagated, total = await _propagate_to_friends(db, record)

        msg = f"Budget group '{record.name}' updated"
        if propagated:
            msg += f" ({propagated}/{total} friends' keys updated)"

        return BudgetGroupResponse(
            message=msg,
            group=_record_to_info(record, total),
        )
    finally:
        db.close()


@router.delete("/{group_id}", response_model=BudgetGroupDeleteResponse)
async def delete_group(group_id: int):
    """Delete a budget group. Removes from all friends' assignments."""
    db = SessionLocal()
    try:
        record = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        # Get affected friends BEFORE deleting (so we can re-merge their remaining groups)
        affected_friends = _get_friends_in_group(db, group_id)

        # Delete the group (junction table rows cascade)
        db.delete(record)
        db.commit()

        # Re-merge settings for affected friends (they may have other groups still)
        for friend in affected_friends:
            if friend.litellm_key:
                try:
                    merged = merge_groups(friend.groups)
                    await litellm_client.update_virtual_key(
                        token=friend.litellm_key,
                        models=merged["models"],
                        tpm_limit=merged["tpm_limit"],
                        rpm_limit=merged["rpm_limit"],
                        max_budget=merged["max_budget"],
                        budget_duration=merged["budget_duration"],
                    )
                    # Update hermes config + restart pod
                    ns = f"friend-{friend.name}"
                    default_model = merged["models"][0] if merged["models"] else "gpt-3.5-turbo"
                    k8s.update_hermes_configmap(ns, default_model, friend.litellm_key)
                    k8s.restart_deployment(ns)
                except Exception as e:
                    logger.warning(f"Failed to update key/config for friend '{friend.name}' after group deletion: {e}")

        return BudgetGroupDeleteResponse(
            message=f"Budget group '{record.name}' deleted (updated {len(affected_friends)} friends)"
        )
    finally:
        db.close()
