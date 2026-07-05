"""State management router — save, restore, list snapshots."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models import (
    StateSaveResponse,
    StateRestoreResponse,
    SnapshotListResponse,
)
from services import state_manager, friend_manager

router = APIRouter(prefix="/api/friends", tags=["state"])


# --- Compatibility routes (frontend calls /{name}/save, /{name}/snapshots, /{name}/restore) ---

@router.post("/{name}/save", response_model=StateSaveResponse)
async def save_state_compat(name: str):
    return await save_state(name)

@router.get("/{name}/snapshots", response_model=SnapshotListResponse)
async def list_snapshots_compat(name: str):
    return await list_snapshots(name)

@router.post("/{name}/restore", response_model=StateRestoreResponse)
async def restore_state_compat(name: str, snapshot_key: str | None = None):
    return await restore_state(name, snapshot_key)


@router.post("/{name}/state/save", response_model=StateSaveResponse)
async def save_state(name: str):
    """Save friend state to MinIO."""
    info = friend_manager.get_friend_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

    if info.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Friend '{name}' is not running (status: {info.status}). Cannot save state."
        )

    try:
        key = state_manager.save_state(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save state: {e}")

    return StateSaveResponse(
        message=f"State saved for '{name}'",
        snapshot_key=key,
    )


@router.get("/{name}/state", response_model=SnapshotListResponse)
async def list_snapshots(name: str):
    """List available snapshots for a friend."""
    info = friend_manager.get_friend_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

    snapshots = state_manager.get_snapshots(name)
    return SnapshotListResponse(friend=name, snapshots=snapshots)


@router.post("/{name}/state/restore", response_model=StateRestoreResponse)
async def restore_state(name: str, snapshot_key: str | None = None):
    """Restore friend state from a snapshot."""
    info = friend_manager.get_friend_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")

    # If no key provided, use the latest snapshot
    if not snapshot_key:
        snapshots = state_manager.get_snapshots(name)
        if not snapshots:
            raise HTTPException(status_code=404, detail=f"No snapshots found for '{name}'")
        snapshot_key = snapshots[0].key

    try:
        result = state_manager.restore_state(name, snapshot_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore state: {e}")

    return StateRestoreResponse(**result)
