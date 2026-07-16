"""Usage tracking router — reads from LiteLLM's database."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import create_engine, text

from config import settings

router = APIRouter(prefix="/api/usage", tags=["usage"])

LITELLM_DB_URL = (
    f"postgresql://{settings.postgres_user}:***"
    f"@{settings.postgres_host}:{settings.postgres_port}/litellm"
)


def _get_litellm_db():
    """Connect to the LiteLLM database (separate DB)."""
    url = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/litellm"
    )
    return create_engine(url, pool_pre_ping=True)


@router.get("")
async def get_usage(period: str = Query("24h", regex=r"^(1h|6h|24h|7d|30d)$")):
    """Get usage summary from LiteLLM logs."""
    engine = _get_litellm_db()
    try:
        interval_map = {
            "1h": "1 hour",
            "6h": "6 hours",
            "24h": "24 hours",
            "7d": "7 days",
            "30d": "30 days",
        }
        interval = interval_map.get(period, "24 hours")

        with engine.connect() as conn:
            # Total requests and tokens
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total_requests,
                    COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as total_tokens,
                    COALESCE(SUM(CAST(spend AS NUMERIC)), 0) as total_cost
                FROM LiteLLM_SpendLogs
                WHERE created_at > NOW() - INTERVAL :interval
            """), {"interval": interval})
            row = result.fetchone()

            total_requests = row[0] if row else 0
            total_tokens = int(row[1]) if row else 0
            total_cost = float(row[2]) if row else 0

            # By model
            result = conn.execute(text("""
                SELECT model, COUNT(*) as requests, COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as tokens
                FROM LiteLLM_SpendLogs
                WHERE created_at > NOW() - INTERVAL :interval
                GROUP BY model
                ORDER BY requests DESC
            """), {"interval": interval})
            by_model = {}
            for r in result.fetchall():
                by_model[r[0] or "unknown"] = {
                    "requests": r[1],
                    "tokens": int(r[2]),
                }

            # By API key (friend)
            result = conn.execute(text("""
                SELECT
                    k.api_key_name,
                    COUNT(*) as requests,
                    COALESCE(SUM(CAST(total_tokens AS BIGINT)), 0) as tokens
                FROM LiteLLM_SpendLogs s
                LEFT JOIN LiteLLM_VerificationTokens k ON s.api_key = k.token
                WHERE s.created_at > NOW() - INTERVAL :interval
                GROUP BY k.api_key_name
                ORDER BY requests DESC
                LIMIT 20
            """), {"interval": interval})
            by_friend = {}
            for r in result.fetchall():
                by_friend[r[0] or "unknown"] = {
                    "requests": r[1],
                    "tokens": int(r[2]),
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
        # LiteLLM DB might not have tables yet
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


@router.get("/models")
async def list_models():
    """List available models from LiteLLM config."""
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
