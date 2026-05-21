"""
SportyTadka API — Main entry point.

Run locally: uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.db import Base, engine
from app.tasks import setup_scheduler, shutdown_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.
    - On startup: create DB tables, start background scheduler
    - On shutdown: stop scheduler, close connections
    """
    logger.info(f"Starting SportyTadka API ({settings.app_env})")

    # Recreate tables with current schema
    # drop_all + create_all ensures schema changes are applied
    # TODO: Replace with Alembic migrations for production data persistence
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables recreated with multi-sport schema")

    # Start background polling scheduler
    setup_scheduler()

    yield

    # Cleanup
    shutdown_scheduler()
    await engine.dispose()
    logger.info("SportyTadka API shut down")


# Create app
app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET"],  # Read-only API for MVP
    allow_headers=["*"],
)

# Routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for Render / monitoring."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.app_env,
    }
