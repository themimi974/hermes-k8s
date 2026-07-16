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
    FriendRecord,
    BudgetGroupRecord,
)
from services import friend_manager
from database import SessionLocal

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
    """Create a new friend — provisions namespace, PVC, deployment, etc."""
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


@router.post("/friends/{name}/assign-group")
async def assign_budget_group(name: str, group_id: int):
    """Assign a friend to a budget group."""
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
        return {"message": f"Friend '{name}' assigned to group '{group.name}'"}
    finally:
        db.close()
