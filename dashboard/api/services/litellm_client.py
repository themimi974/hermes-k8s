"""LiteLLM API client — manages virtual keys."""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

LITELLM_BASE = f"http://{settings.litellm_host}:{settings.litellm_port}"
HEADERS = {"Authorization": f"Bearer {settings.litellm_master_key}"}


def _hash_key(key: str) -> str:
    """SHA-256 hash of a virtual key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


async def create_virtual_key(
    friend_name: str,
    models: list[str],
    tpm_limit: int = 100000,
    rpm_limit: int = 1000,
    max_budget: float = 50.0,
    budget_duration: str = "30d",
    team_id: Optional[str] = None,
) -> dict:
    """Create a LiteLLM virtual key for a friend.

    Returns dict with: key, key_name, key_hash, token
    """
    payload = {
        "key_name": f"friend-{friend_name}",
        "models": models,
        "tpm_limit": tpm_limit,
        "rpm_limit": rpm_limit,
        "max_budget": max_budget,
        "budget_duration": budget_duration,
        "metadata": {"friend": friend_name, "type": "friend-key"},
    }
    if team_id:
        payload["team_id"] = team_id

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LITELLM_BASE}/key/generate",
            json=payload,
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

    key = data.get("key", "")
    token = data.get("token", "")
    key_hash = _hash_key(key) if key else ""

    logger.info(f"Created LiteLLM key for friend '{friend_name}': {key[:12]}...")
    return {
        "key": key,
        "token": token,
        "key_name": f"friend-{friend_name}",
        "key_hash": key_hash,
    }


async def delete_virtual_key(token: str) -> bool:
    """Delete a LiteLLM virtual key by token."""
    if not token:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LITELLM_BASE}/key/delete",
            json={"key": token},
            headers=HEADERS,
        )
        if resp.status_code == 200:
            logger.info(f"Deleted LiteLLM key: {token[:12]}...")
            return True
        logger.warning(f"Failed to delete LiteLLM key: {resp.status_code} {resp.text}")
        return False


async def update_virtual_key(
    token: str,
    models: Optional[list[str]] = None,
    tpm_limit: Optional[int] = None,
    rpm_limit: Optional[int] = None,
    max_budget: Optional[float] = None,
    budget_duration: Optional[str] = None,
) -> bool:
    """Update a LiteLLM virtual key."""
    if not token:
        return False

    payload = {"key": token}
    if models is not None:
        payload["models"] = models
    if tpm_limit is not None:
        payload["tpm_limit"] = tpm_limit
    if rpm_limit is not None:
        payload["rpm_limit"] = rpm_limit
    if max_budget is not None:
        payload["max_budget"] = max_budget
    if budget_duration is not None:
        payload["budget_duration"] = budget_duration

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LITELLM_BASE}/key/update",
            json=payload,
            headers=HEADERS,
        )
        if resp.status_code == 200:
            logger.info(f"Updated LiteLLM key: {token[:12]}...")
            return True
        logger.warning(f"Failed to update LiteLLM key: {resp.status_code} {resp.text}")
        return False


async def list_virtual_keys() -> list[dict]:
    """List all LiteLLM virtual keys."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{LITELLM_BASE}/key/list",
            headers=HEADERS,
        )
        if resp.status_code == 200:
            return resp.json().get("keys", [])
    return []


async def get_key_info(token: str) -> Optional[dict]:
    """Get info about a specific LiteLLM key."""
    if not token:
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LITELLM_BASE}/key/info",
            json={"key": token},
            headers=HEADERS,
        )
        if resp.status_code == 200:
            return resp.json()
    return None
