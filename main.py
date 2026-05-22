"""
SportyTadka API — Main entry point.
Run locally: uvicorn main:app --reload --port 8000
"""

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1 import api_router
from app.core.config import get_settings
from app.db import Base, engine
from app.tasks import setup_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Custom CORS middleware that supports wildcard subdomains
# ---------------------------------------------------------------------------

# Patterns that are always allowed
ALLOWED_ORIGIN_PATTERNS = [
    re.compile(r"https://.*\.vercel\.app$"),       # All Vercel preview deployments
    re.compile(r"https://sportytadka\.com$"),       # Production
    re.compile(r"https://www\.sportytadka\.com$"),  # Production www
    re.compile(r"http://localhost:\d+$"),            # Local development
]


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """CORS middleware that allows any Vercel subdomain + configured origins."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")

        # Check if origin matches any allowed pattern
        is_allowed = False
        for pattern in ALLOWED_ORIGIN_PATTERNS:
            if pattern.match(origin):
                is_allowed = True
                break

        # Also check explicit origins from env var
        if not is_allowed and origin in settings.cors_origin_list:
            is_allowed = True

        # Handle preflight OPTIONS
        if request.method == "OPTIONS" and is_allowed:
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "86400",
                },
            )

        response = await call_next(request)

        if is_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"

        return response


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting SportyTadka API ({settings.app_env})")

    # Create tables if they don't exist — safe to run on every startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    setup_scheduler()
    yield

    shutdown_scheduler()
    await engine.dispose()
    logger.info("SportyTadka API shut down")


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# Use our custom CORS middleware instead of FastAPI's built-in
app.add_middleware(DynamicCORSMiddleware)

# Routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.app_env,
    }
