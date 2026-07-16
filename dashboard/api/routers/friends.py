"""Friends CRUD router."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from models import (
    FriendCreate,
    FriendInfo,
    FriendDetail,
    CreateResponse,
    DeleteResponse,
    SnapshotListResponse,
    FriendSnapshot,
    FriendRecord,
    BudgetGroupRecord,
)
from services import friend_manager, litellm_client
from database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["friends"])


def _enrich_friend(info: FriendInfo) -> FriendInfo:
    """Add budget group info from DB."""
    db = SessionLocal()
    try:
        record = db.query(FriendRecord).filter(FriendRecord.name == info.name).first()
        if record:
            info.budget_group_id = record.budget_group_id
            info.litellm_key = record.litellm_key[:8] + "..." if record.litellm_key else None
            if record.budget_group_id:
                group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == record.budget_group_id).first()
                if group:
                    info.budget_group_name = group.name
        return info
    finally:
        db.close()


@router.get("/friends", response_model=list[FriendInfo])
async def list_friends():
    """List all friend namespaces with status."""
    friends = friend_manager.list_friends()
    return [_enrich_friend(f) for f in friends]


@router.get("/friends/{name}", response_model=FriendDetail)
async def get_friend(name: str):
    """Get details for a single friend."""
    info = friend_manager.get_friend_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")
    return _enrich_friend(info)


@router.post("/friends", response_model=CreateResponse, status_code=201)
async def create_friend(body: FriendCreate):
    """Create a new friend — provisions namespace, PVC, deployment, and LiteLLM key."""
    existing = friend_manager.get_friend_info(body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Friend '{body.name}' already exists")

    try:
        info = friend_manager.create_friend(body.name, body.username, body.password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create friend: {e}")

    # Create LiteLLM virtual key
    db = SessionLocal()
    try:
        record = db.query(FriendRecord).filter(FriendRecord.name == body.name).first()
        if not record:
            record = FriendRecord(
                name=body.name,
                username=body.username,
                namespace=f"friend-{body.name}",
            )
            db.add(record)
            db.commit()
            db.refresh(record)

        # Get budget group settings for the key
        models = ["gpt-3.5-turbo"]
        tpm_limit = 100000
        rpm_limit = 1000
        max_budget = 50.0
        budget_duration = "30d"

        if record.budget_group_id:
            group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == record.budget_group_id).first()
            if group:
                models = group.models or ["gpt-3.5-turbo"]
                tpm_limit = group.tpm_limit
                rpm_limit = group.rpm_limit
                max_budget = group.max_budget
                budget_duration = group.budget_duration

        key_data = await litellm_client.create_virtual_key(
            friend_name=body.name,
            models=models,
            tpm_limit=tpm_limit,
            rpm_limit=rpm_limit,
            max_budget=max_budget,
            budget_duration=budget_duration,
        )

        # Store the full key (token) for later use in updates/deletions
        record.litellm_key = key_data["key"]
        record.litellm_key_hash = key_data["key_hash"]
        db.commit()
        logger.info(f"Created LiteLLM key for friend '{body.name}'")
    except Exception as e:
        logger.warning(f"Failed to create LiteLLM key for '{body.name}': {e}")
    finally:
        db.close()

    return CreateResponse(
        message=f"Friend '{body.name}' created successfully",
        friend=info,
    )


@router.delete("/friends/{name}", response_model=DeleteResponse)
async def delete_friend(name: str):
    """Delete a friend and all associated resources (cascading)."""
    existing = friend_manager.get_friend_info(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

    # Delete LiteLLM virtual key first
    db = SessionLocal()
    try:
        record = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if record and record.litellm_key:
            # Use the stored key directly for deletion
            await litellm_client.delete_virtual_key(record.litellm_key)
    except Exception as e:
        logger.warning(f"Failed to delete LiteLLM key for '{name}': {e}")
    finally:
        db.close()

    try:
        friend_manager.delete_friend(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete friend: {e}")

    # Delete DB record
    db = SessionLocal()
    try:
        record = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if record:
            db.delete(record)
            db.commit()
    finally:
        db.close()

    return DeleteResponse(
        message=f"Friend '{name}' deleted",
        namespace=f"friend-{name}",
    )


@router.post("/friends/{name}/assign-group")
async def assign_budget_group(name: str, group_id: int):
    """Assign a friend to a budget group and update their LiteLLM key."""
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            # Create DB record if friend exists in k8s but not in DB
            friend = FriendRecord(name=name, username=name, namespace=f"friend-{name}")
            db.add(friend)

        group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        friend.budget_group_id = group_id
        db.commit()

        # Update LiteLLM key with new group settings
        if friend.litellm_key:
            await litellm_client.update_virtual_key(
                token=friend.litellm_key,
                models=group.models or ["gpt-3.5-turbo"],
                tpm_limit=group.tpm_limit,
                rpm_limit=group.rpm_limit,
                max_budget=group.max_budget,
                budget_duration=group.budget_duration,
            )
            logger.info(f"Updated LiteLLM key for friend '{name}' with group '{group.name}'")

        return {"message": f"Friend '{name}' assigned to group '{group.name}'"}
    finally:
        db.close()
