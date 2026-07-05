"""Friends CRUD router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models import (
    FriendCreate,
    FriendInfo,
    FriendDetail,
    CreateResponse,
    DeleteResponse,
    SnapshotListResponse,
    FriendSnapshot,
)
from services import friend_manager

router = APIRouter(prefix="/api", tags=["friends"])


@router.get("/friends", response_model=list[FriendInfo])
async def list_friends():
    """List all friend namespaces with status."""
    return friend_manager.list_friends()


@router.get("/friends/{name}", response_model=FriendDetail)
async def get_friend(name: str):
    """Get details for a single friend."""
    info = friend_manager.get_friend_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Friend '{name}' not found")
    return info


@router.post("/friends", response_model=CreateResponse, status_code=201)
async def create_friend(body: FriendCreate):
    """Create a new friend — provisions namespace, PVC, deployment, etc."""
    # Check if already exists
    existing = friend_manager.get_friend_info(body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Friend '{body.name}' already exists")

    try:
        info = friend_manager.create_friend(body.name, body.username, body.password)
    except Exception as e:
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

    try:
        friend_manager.delete_friend(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete friend: {e}")

    return DeleteResponse(
        message=f"Friend '{name}' deleted",
        namespace=f"friend-{name}",
    )
