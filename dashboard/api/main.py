"""Hermes Dashboard API — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from config import settings
from routers import health, friends, budget_groups, usage

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
    yield
    logger.info("Shutting down Hermes Dashboard API...")


app = FastAPI(
    title="Hermes Dashboard API",
    description="Manage friend namespaces, budget groups, and usage on hermes-k8s",
    version="2.0.0",
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
app.include_router(budget_groups.router)
app.include_router(usage.router)


@app.get("/")
async def root():
    return {
        "service": "hermes-dashboard-api",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/api/config")
async def get_config():
    """Return runtime config for the frontend (domain, TLS method)."""
    return {
        "domain": settings.friend_domain,
        "tls_method": settings.tls_method,
        "tls_cert_resolver": settings.tls_cert_resolver,
    }
