"""Hermes Dashboard API — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import health, friends, state
from services.minio_client import ensure_bucket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dashboard-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Starting Hermes Dashboard API...")
    init_db()
    logger.info("Database tables initialized")
    try:
        ensure_bucket()
        logger.info("MinIO bucket ready")
    except Exception as e:
        logger.warning(f"MinIO bucket check failed (non-fatal): {e}")
    yield
    logger.info("Shutting down Hermes Dashboard API...")


app = FastAPI(
    title="Hermes Dashboard API",
    description="Manage friend namespaces, deployments, and state on hermes-k8s",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(friends.router)
app.include_router(state.router)


@app.get("/")
async def root():
    return {
        "service": "hermes-dashboard-api",
        "version": "1.0.0",
        "docs": "/docs",
    }
