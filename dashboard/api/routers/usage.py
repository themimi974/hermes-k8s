"""Usage tracking router — reads from LiteLLM's database.

Provides per-friend, per-model, and friend×model matrix views.
All queries hit the LiteLLM PostgreSQL database (litellm DB).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import create_engine, text
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/api/usage", tags=["usage"])

LITELLM_DB_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/litellm_db"
)

# Valid period aliases
INTERVAL_MAP = {
    "1h": "1 hour",
    "6h": "6 hours",
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
}


def _get_litellm_db():
    """Connect to the LiteLLM database (separate DB)."""
    url = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}"
        f":{settings.postgres_port}/litellm_db"
    )
    return create_engine(url, pool_pre_ping=True)


def _safe_interval(period: str) -> str:
    return INTERVAL_MAP.get(period, "24 hours")


# ── Global overview ────────────────────────────────────────────────


@router.get("")
async def get_usage(period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$")):
    """Get global usage summary from LiteLLM logs."""
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            # Total
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total_requests,
                    COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as total_tokens,
                    COALESCE(SUM(CAST(spend AS NUMERIC)), 0) as total_cost
                FROM "LiteLLM_SpendLogs"
                WHERE "startTime" > NOW() - INTERVAL :interval
            """), {"interval": interval})
            row = result.fetchone()
            total_requests = row[0] if row else 0
            total_tokens = int(row[1]) if row else 0
            total_cost = float(row[2]) if row else 0

            # By model
            result = conn.execute(text("""
                SELECT model, COUNT(*) as requests,
                       COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs"
                WHERE "startTime" > NOW() - INTERVAL :interval
                GROUP BY model
                ORDER BY requests DESC
            """), {"interval": interval})
            by_model = {}
            for r in result.fetchall():
                by_model[r[0] or "unknown"] = {
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                }

            # By friend (API key)
            result = conn.execute(text("""
                SELECT k.key_alias,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs" s
                LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE s."startTime" > NOW() - INTERVAL :interval
                GROUP BY k.key_alias
                ORDER BY requests DESC
                LIMIT 50
            """), {"interval": interval})
            by_friend = {}
            for r in result.fetchall():
                by_friend[r[0] or "unknown"] = {
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                }

            return {
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "by_model": by_model,
                "by_friend": by_friend,
                "period": period,
            }
    except Exception as e:
        return {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "by_model": {},
            "by_friend": {},
            "period": period,
            "note": f"LiteLLM DB not ready: {e}",
        }
    finally:
        engine.dispose()


# ── Per-friend usage ───────────────────────────────────────────────


@router.get("/friends")
async def usage_by_friends(period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$")):
    """List all friends with their total usage stats."""
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT k.key_alias,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost,
                       MIN(s."startTime") as first_seen,
                       MAX(s."startTime") as last_seen
                FROM "LiteLLM_SpendLogs" s
                LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE s."startTime" > NOW() - INTERVAL :interval
                  AND k.key_alias IS NOT NULL
                GROUP BY k.key_alias
                ORDER BY tokens DESC
            """), {"interval": interval})

            friends = []
            for r in result.fetchall():
                name = r[0]
                # Strip "friend-" prefix if present (LiteLLM key naming)
                display_name = name.replace("friend-", "") if name and name.startswith("friend-") else name
                friends.append({
                    "name": display_name,
                    "key_name": name,
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                    "first_seen": r[4].isoformat() if r[4] else None,
                    "last_seen": r[5].isoformat() if r[5] else None,
                })
            return {"friends": friends, "period": period}
    except Exception as e:
        return {"friends": [], "period": period, "note": f"LiteLLM DB not ready: {e}"}
    finally:
        engine.dispose()


@router.get("/friends/{name}")
async def usage_for_friend(
    name: str,
    period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$"),
):
    """Get usage breakdown by model for a specific friend."""
    # Try both "friend-{name}" and "{name}" key patterns
    key_patterns = [f"friend-{name}", name]
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            # Build IN clause for key patterns
            placeholders = ", ".join([f":kp{i}" for i in range(len(key_patterns))])
            params = {"interval": interval}
            for i, kp in enumerate(key_patterns):
                params[f"kp{i}"] = kp

            # Total for this friend
            result = conn.execute(text(f"""
                SELECT COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs" s
                JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE k.key_alias IN ({placeholders})
                  AND s."startTime" > NOW() - INTERVAL :interval
            """), params)
            row = result.fetchone()
            total = {
                "requests": row[0] if row else 0,
                "tokens": int(row[1]) if row else 0,
                "cost": round(float(row[2]), 4) if row else 0,
            }

            # Per-model breakdown
            result = conn.execute(text(f"""
                SELECT s.model,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs" s
                JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE k.key_alias IN ({placeholders})
                  AND s."startTime" > NOW() - INTERVAL :interval
                GROUP BY s.model
                ORDER BY tokens DESC
            """), params)

            by_model = []
            for r in result.fetchall():
                by_model.append({
                    "model": r[0] or "unknown",
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                })

            return {
                "friend": name,
                "total": total,
                "by_model": by_model,
                "period": period,
            }
    except Exception as e:
        return {
            "friend": name,
            "total": {"requests": 0, "tokens": 0, "cost": 0},
            "by_model": [],
            "period": period,
            "note": f"LiteLLM DB not ready: {e}",
        }
    finally:
        engine.dispose()


# ── Per-model usage ────────────────────────────────────────────────


@router.get("/models")
async def usage_by_models(period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$")):
    """List all models with their total usage stats."""
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT model,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost,
                       MIN("startTime") as first_used,
                       MAX("startTime") as last_used
                FROM "LiteLLM_SpendLogs"
                WHERE "startTime" > NOW() - INTERVAL :interval
                GROUP BY model
                ORDER BY tokens DESC
            """), {"interval": interval})

            models = []
            for r in result.fetchall():
                models.append({
                    "model": r[0] or "unknown",
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                    "first_used": r[4].isoformat() if r[4] else None,
                    "last_used": r[5].isoformat() if r[5] else None,
                })
            return {"models": models, "period": period}
    except Exception as e:
        return {"models": [], "period": period, "note": f"LiteLLM DB not ready: {e}"}
    finally:
        engine.dispose()


@router.get("/models/{model_id:path}")
async def usage_for_model(
    model_id: str,
    period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$"),
):
    """Get usage breakdown by friend for a specific model."""
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            # Total for this model
            result = conn.execute(text("""
                SELECT COUNT(*) as requests,
                       COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs"
                WHERE model = :model
                  AND "startTime" > NOW() - INTERVAL :interval
            """), {"model": model_id, "interval": interval})
            row = result.fetchone()
            total = {
                "requests": row[0] if row else 0,
                "tokens": int(row[1]) if row else 0,
                "cost": round(float(row[2]), 4) if row else 0,
            }

            # Per-friend breakdown for this model
            result = conn.execute(text("""
                SELECT k.key_alias,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs" s
                LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE s.model = :model
                  AND s."startTime" > NOW() - INTERVAL :interval
                GROUP BY k.key_alias
                ORDER BY tokens DESC
            """), {"model": model_id, "interval": interval})

            by_friend = []
            for r in result.fetchall():
                name = r[0] or "unknown"
                display_name = name.replace("friend-", "") if name.startswith("friend-") else name
                by_friend.append({
                    "name": display_name,
                    "key_name": name,
                    "requests": r[1],
                    "tokens": int(r[2]),
                    "cost": round(float(r[3]), 4),
                })

            return {
                "model": model_id,
                "total": total,
                "by_friend": by_friend,
                "period": period,
            }
    except Exception as e:
        return {
            "model": model_id,
            "total": {"requests": 0, "tokens": 0, "cost": 0},
            "by_friend": [],
            "period": period,
            "note": f"LiteLLM DB not ready: {e}",
        }
    finally:
        engine.dispose()


# ── Friend × Model matrix ──────────────────────────────────────────


@router.get("/matrix")
async def usage_matrix(period: str = Query("24h", pattern=r"^(1h|6h|24h|7d|30d)$")):
    """Get friend × model usage matrix (for cross-table / heatmap view).

    Returns:
        rows: list of friend names
        cols: list of model names
        cells: dict keyed by "friend|model" → {requests, tokens, cost}
    """
    engine = _get_litellm_db()
    try:
        interval = _safe_interval(period)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT k.key_alias, s.model,
                       COUNT(*) as requests,
                       COALESCE(SUM(CAST(s.total_tokens AS BIGINT)), 0) as tokens,
                       COALESCE(SUM(CAST(s.spend AS NUMERIC)), 0) as cost
                FROM "LiteLLM_SpendLogs" s
                LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token
                WHERE s."startTime" > NOW() - INTERVAL :interval
                GROUP BY k.key_alias, s.model
                ORDER BY k.key_alias, tokens DESC
            """), {"interval": interval})

            friends_set = set()
            models_set = set()
            cells = {}

            for r in result.fetchall():
                raw_name = r[0] or "unknown"
                model = r[1] or "unknown"
                display_name = raw_name.replace("friend-", "") if raw_name.startswith("friend-") else raw_name

                friends_set.add(display_name)
                models_set.add(model)
                cells[f"{display_name}|{model}"] = {
                    "requests": r[2],
                    "tokens": int(r[3]),
                    "cost": round(float(r[4]), 4),
                }

            return {
                "friends": sorted(friends_set),
                "models": sorted(models_set),
                "cells": cells,
                "period": period,
            }
    except Exception as e:
        return {
            "friends": [],
            "models": [],
            "cells": {},
            "period": period,
            "note": f"LiteLLM DB not ready: {e}",
        }
    finally:
        engine.dispose()


# ── Legacy endpoint ────────────────────────────────────────────────


@router.get("/litellm-models")
async def list_litellm_models():
    """List available models from LiteLLM config (proxy endpoint)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://{settings.litellm_host}:{settings.litellm_port}/v1/models",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
            if resp.status_code == 200:
                return resp.json()
            return {"data": []}
    except Exception:
        return {"data": []}
