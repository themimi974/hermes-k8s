"""Models management — CRUD + LiteLLM config sync."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from database import get_db
from models import (
    ModelCreate,
    ModelInfo,
    ModelRecord,
    ModelResponse,
    ModelTestResult,
    ModelUpdate,
)
from services.litellm_config import apply_config, generate_config

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)


def _refresh_config() -> bool:
    """Regenerate and apply LiteLLM config from all enabled models."""
    db = next(get_db())
    try:
        models = db.query(ModelRecord).filter(ModelRecord.enabled.is_(True)).all()
        config_yaml = generate_config(models)
        return apply_config(config_yaml)
    finally:
        db.close()


def _to_info(m: ModelRecord) -> ModelInfo:
    return ModelInfo(
        id=m.id,
        name=m.name,
        model_id=m.model_id,
        api_type=m.api_type,
        api_key=m.api_key[:12] + "..." if len(m.api_key) > 12 else m.api_key,
        api_base=m.api_base,
        context_length=m.context_length,
        max_tokens=m.max_tokens,
        enabled=m.enabled,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("/", response_model=list[ModelInfo])
async def list_models():
    db = next(get_db())
    try:
        models = db.query(ModelRecord).order_by(ModelRecord.name).all()
        return [_to_info(m) for m in models]
    finally:
        db.close()


@router.post("/", response_model=ModelResponse, status_code=201)
async def create_model(body: ModelCreate):
    db = next(get_db())
    try:
        existing = db.query(ModelRecord).filter(ModelRecord.name == body.name).first()
        if existing:
            raise HTTPException(409, f"Model '{body.name}' already exists")

        model = ModelRecord(**body.model_dump())
        db.add(model)
        db.commit()
        db.refresh(model)

        if not _refresh_config():
            logger.warning("Model created but LiteLLM config update failed — pod may need manual restart")

        return ModelResponse(message=f"Model '{model.name}' created", model=_to_info(model))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(model_id: int, body: ModelUpdate):
    db = next(get_db())
    try:
        model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if not model:
            raise HTTPException(404, "Model not found")

        updates = body.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(model, k, v)
        db.commit()
        db.refresh(model)

        if not _refresh_config():
            logger.warning("Model updated but LiteLLM config update failed")

        return ModelResponse(message=f"Model '{model.name}' updated", model=_to_info(model))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@router.delete("/{model_id}")
async def delete_model(model_id: int):
    db = next(get_db())
    try:
        model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if not model:
            raise HTTPException(404, "Model not found")

        name = model.name
        db.delete(model)
        db.commit()

        if not _refresh_config():
            logger.warning("Model deleted but LiteLLM config update failed")

        return {"message": f"Model '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@router.post("/{model_id}/test", response_model=ModelTestResult)
async def test_model(model_id: int):
    """Test a model by sending a minimal completion request."""
    import httpx

    db = next(get_db())
    try:
        model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if not model:
            raise HTTPException(404, "Model not found")

        # Build test request based on API type
        if model.api_type == "anthropic":
            url = f"{model.api_base}/v1/messages" if model.api_base else "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": model.api_key, "anthropic-version": "2023-06-01"}
            payload = {
                "model": model.model_id,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say hi"}],
            }
        else:
            base = model.api_base or "https://api.openai.com/v1"
            url = f"{base}/chat/completions"
            headers = {"Authorization": f"Bearer {model.api_key}"}
            payload = {
                "model": model.model_id,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say hi"}],
            }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                latency = int((time.monotonic() - start) * 1000)
                if resp.status_code < 300:
                    return ModelTestResult(model_id=model.model_id, success=True, latency_ms=latency)
                return ModelTestResult(
                    model_id=model.model_id,
                    success=False,
                    latency_ms=latency,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return ModelTestResult(model_id=model.model_id, success=False, latency_ms=latency, error=str(e))
    finally:
        db.close()
