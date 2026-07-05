"""Health check router."""
from datetime import datetime, timezone

from fastapi import APIRouter

from models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
    )
