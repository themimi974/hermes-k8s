"""Friends CRUD router — uses junction table for multi-group assignment."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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
    GroupAssignment,
    ResourceUpdate,
)
from services import friend_manager, litellm_client, k8s
from services.merge import merge_groups, get_friend_merged_settings
from database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["friends"])


def _enrich_friend(info: FriendInfo) -> FriendInfo:
    """Add budget group info from DB via junction table."""
    db = SessionLocal()
    try:
        record = db.query(FriendRecord).filter(FriendRecord.name == info.name).first()
        if record:
            info.litellm_key = record.litellm_key[:8] + "..." if record.litellm_key else None
            # Read from junction table (multi-group)
            groups = record.groups
            if groups:
                info.budget_groups = [g.name for g in groups]
                # Keep first group as primary for backward compat
                info.budget_group_id = groups[0].id
                info.budget_group_name = groups[0].name
            # Per-friend resource overrides
            info.cpu_request = record.cpu_request
            info.cpu_limit = record.cpu_limit
            info.memory_request = record.memory_request
            info.memory_limit = record.memory_limit
            info.storage_size = record.storage_size
        return info
    finally:
        db.close()


async def _update_friend_config(name: str, friend_record: FriendRecord):
    """Update hermes config ConfigMap + restart pod after group/key changes.

    Recomputes the merged model list from assigned groups and updates
    the ConfigMap so Hermes points at the correct default model.
    Also creates missing k8s resources (ConfigMap, Secret, volume mounts).
    """
    ns = f"friend-{name}"
    try:
        groups = friend_record.groups
        merged = merge_groups(groups) if groups else merge_groups([])

        # First model in merged list becomes the default
        default_model = merged["models"][0] if merged["models"] else "gpt-3.5-turbo"

        # Update ConfigMap with new model + key
        if friend_record.litellm_key:
            # Create ConfigMap if missing, then update
            k8s.create_hermes_configmap(ns, default_model, friend_record.litellm_key, merged["models"])
            # Create Secret if missing
            k8s.create_litellm_secret(ns, friend_record.litellm_key)
            # Ensure deployment has volume mounts
            k8s.ensure_deployment_volume_mounts(ns, friend_record.litellm_key)
            # Restart pod to pick up changes
            k8s.restart_deployment(ns)
            logger.info(f"Updated hermes config + restarted pod for '{name}' (model: {default_model})")
    except Exception as e:
        logger.warning(f"Failed to update config for '{name}': {e}")


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
    """Create a new friend — provisions namespace, PVC, deployment, and LiteLLM key.

    Creates hermes config ConfigMap + Secret so the friend pod uses LiteLLM.
    """
    existing = friend_manager.get_friend_info(body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Friend '{body.name}' already exists")

    # 1. Create DB record first
    db = SessionLocal()
    try:
        record = FriendRecord(
            name=body.name,
            username=body.username,
            namespace=f"friend-{body.name}",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    finally:
        db.close()

    # 2. Create LiteLLM virtual key
    litellm_key = None
    try:
        key_data = await litellm_client.create_virtual_key(
            friend_name=body.name,
            models=["gpt-3.5-turbo"],
            tpm_limit=100000,
            rpm_limit=1000,
            max_budget=50.0,
            budget_duration="30d",
        )
        litellm_key = key_data["key"]

        # Store key in DB
        db = SessionLocal()
        try:
            record = db.query(FriendRecord).filter(FriendRecord.name == body.name).first()
            if record:
                record.litellm_key = key_data["key"]
                record.litellm_key_hash = key_data["key_hash"]
                db.commit()
        finally:
            db.close()

        logger.info(f"Created LiteLLM key for friend '{body.name}'")
    except Exception as e:
        logger.warning(f"Failed to create LiteLLM key for '{body.name}': {e}")

    # 3. Create k8s resources (with LiteLLM config if key was created)
    try:
        info = friend_manager.create_friend(
            body.name, body.username, body.password,
            litellm_key=litellm_key,
        )
    except Exception as e:
        # Clean up DB record on failure
        db = SessionLocal()
        try:
            record = db.query(FriendRecord).filter(FriendRecord.name == body.name).first()
            if record:
                db.delete(record)
                db.commit()
        finally:
            db.close()
        raise HTTPException(status_code=500, detail=f"Failed to create friend: {e}")

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


# ── Multi-group assignment ────────────────────────────────────────


@router.post("/friends/{name}/groups")
async def assign_groups(name: str, body: GroupAssignment):
    """Assign a friend to one or more budget groups (replaces current assignments).

    Merges settings across all assigned groups, updates the LiteLLM key,
    and refreshes the hermes config in the friend pod.
    """
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            friend = FriendRecord(name=name, username=name, namespace=f"friend-{name}")
            db.add(friend)
            db.flush()

        # Fetch requested groups
        groups = []
        for gid in body.group_ids:
            group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == gid).first()
            if not group:
                raise HTTPException(status_code=404, detail=f"Budget group {gid} not found")
            groups.append(group)

        # Replace assignments via junction table
        friend.groups = groups
        db.commit()
        db.refresh(friend)

        # Merge settings and update LiteLLM key
        merged = merge_groups(groups)
        if friend.litellm_key:
            await litellm_client.update_virtual_key(
                token=friend.litellm_key,
                models=merged["models"],
                tpm_limit=merged["tpm_limit"],
                rpm_limit=merged["rpm_limit"],
                max_budget=merged["max_budget"],
                budget_duration=merged["budget_duration"],
            )
            logger.info(f"Updated LiteLLM key for '{name}' with {len(groups)} groups")

            # Update hermes config + restart pod
            await _update_friend_config(name, friend)

        group_names = [g.name for g in groups]
        return {
            "message": f"Friend '{name}' assigned to groups: {', '.join(group_names)}",
            "groups": group_names,
            "merged": merged,
        }
    finally:
        db.close()


@router.post("/friends/{name}/groups/{group_id}")
async def add_group(name: str, group_id: int):
    """Add a single group to a friend's assignments (without replacing others)."""
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            friend = FriendRecord(name=name, username=name, namespace=f"friend-{name}")
            db.add(friend)
            db.flush()

        group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        # Add if not already assigned
        if group not in friend.groups:
            friend.groups.append(group)
            db.commit()
            db.refresh(friend)

        # Re-merge and refresh/update LiteLLM key
        merged = merge_groups(friend.groups)
        key_data = await litellm_client.refresh_key(
            friend_name=name,
            models=merged["models"],
            old_key=friend.litellm_key,
            tpm_limit=merged["tpm_limit"],
            rpm_limit=merged["rpm_limit"],
            max_budget=merged["max_budget"],
            budget_duration=merged["budget_duration"],
        )
        new_key = key_data.get("key", friend.litellm_key)
        was_refreshed = key_data.get("was_refreshed", False)
        
        # Update friend record if key was refreshed
        if was_refreshed and new_key != friend.litellm_key:
            db2 = SessionLocal()
            try:
                rec = db2.query(FriendRecord).filter(FriendRecord.name == name).first()
                if rec:
                    rec.litellm_key = new_key
                    rec.litellm_key_hash = key_data.get("key_hash", "")
                    db2.commit()
            finally:
                db2.close()
            friend.litellm_key = new_key
            logger.info(f"Refreshed LiteLLM key for '{name}'")

        # Update hermes config + restart pod
        await _update_friend_config(name, friend)

        return {
            "message": f"Added group '{group.name}' to friend '{name}'",
            "groups": [g.name for g in friend.groups],
            "merged": merged,
            "key_refreshed": was_refreshed,
        }
    finally:
        db.close()


@router.delete("/friends/{name}/groups/{group_id}")
async def remove_group(name: str, group_id: int):
    """Remove a single group from a friend's assignments."""
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

        group = db.query(BudgetGroupRecord).filter(BudgetGroupRecord.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail=f"Budget group {group_id} not found")

        if group in friend.groups:
            friend.groups.remove(group)
            db.commit()
            db.refresh(friend)

        # Re-merge and refresh/update LiteLLM key
        merged = merge_groups(friend.groups)
        key_data = await litellm_client.refresh_key(
            friend_name=name,
            models=merged["models"],
            old_key=friend.litellm_key,
            tpm_limit=merged["tpm_limit"],
            rpm_limit=merged["rpm_limit"],
            max_budget=merged["max_budget"],
            budget_duration=merged["budget_duration"],
        )
        new_key = key_data.get("key", friend.litellm_key)
        was_refreshed = key_data.get("was_refreshed", False)
        
        # Update friend record if key was refreshed
        if was_refreshed and new_key != friend.litellm_key:
            db2 = SessionLocal()
            try:
                rec = db2.query(FriendRecord).filter(FriendRecord.name == name).first()
                if rec:
                    rec.litellm_key = new_key
                    rec.litellm_key_hash = key_data.get("key_hash", "")
                    db2.commit()
            finally:
                db2.close()
            friend.litellm_key = new_key
            logger.info(f"Refreshed LiteLLM key for '{name}'")

        # Update hermes config + restart pod
        await _update_friend_config(name, friend)

        return {
            "message": f"Updated groups for '{name}'",
            "groups": [g.name for g in friend.groups],
            "merged": merged,
            "key_refreshed": was_refreshed,
        }
    finally:
        db.close()


@router.get("/friends/{name}/groups")
async def get_friend_groups(name: str):
    """Get all groups assigned to a friend with merged settings."""
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

        groups = friend.groups
        merged = merge_groups(groups)

        return {
            "friend": name,
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "models": g.models or [],
                    "tpm_limit": g.tpm_limit,
                    "rpm_limit": g.rpm_limit,
                    "max_budget": g.max_budget,
                    "budget_duration": g.budget_duration,
                }
                for g in groups
            ],
            "merged": merged,
        }
    finally:
        db.close()


# ── Per-friend resource overrides ─────────────────────────────────


@router.put("/friends/{name}/resources")
async def update_friend_resources(name: str, body: ResourceUpdate):
    """Update per-friend resource overrides (CPU, memory, storage).

    Set a field to null to clear the override and revert to defaults.
    """
    db = SessionLocal()
    try:
        friend = db.query(FriendRecord).filter(FriendRecord.name == name).first()
        if not friend:
            raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

        overrides = body.model_dump(exclude_unset=True)
        for key, value in overrides.items():
            setattr(friend, key, value)
        db.commit()

        return {
            "message": f"Resources updated for friend '{name}'",
            "overrides": {
                "cpu_request": friend.cpu_request,
                "cpu_limit": friend.cpu_limit,
                "memory_request": friend.memory_request,
                "memory_limit": friend.memory_limit,
                "storage_size": friend.storage_size,
            },
        }
    finally:
        db.close()


# ── Legacy endpoint (backward compat) ────────────────────────────


@router.post("/friends/{name}/assign-group")
async def assign_budget_group(name: str, group_id: int):
    """Legacy: assign a friend to a single budget group. Use /groups instead."""
    return await assign_groups(name, GroupAssignment(group_ids=[group_id]))
