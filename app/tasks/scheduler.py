"""
Background scheduler — runs polling, content pipeline, and live commentary.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.cache import cache
from app.core.config import get_settings
from app.tasks.ingestion import ingest_matches
from app.tasks.content_pipeline import run_content_pipeline
from app.tasks.live_commentary import update_live_commentary

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


def _run_async(coro_func):
    async def wrapper():
        try:
            await coro_func()
        except Exception as e:
            logger.error(f"Scheduled task error: {e}", exc_info=True)
    return wrapper


def setup_scheduler() -> None:
    # Match ingestion — polls all sport APIs
    scheduler.add_job(
        _run_async(ingest_matches),
        "interval",
        seconds=settings.live_match_poll_interval,
        id="ingest_matches",
        replace_existing=True,
        max_instances=1,
    )

    # Live commentary — runs every 30s, only generates AI when score changes
    scheduler.add_job(
        _run_async(update_live_commentary),
        "interval",
        seconds=30,
        id="live_commentary",
        replace_existing=True,
        max_instances=1,
    )

    # Cache cleanup
    async def cleanup():
        removed = cache.cleanup_expired()
        if removed:
            logger.debug(f"Cache cleanup: removed {removed} expired entries")

    scheduler.add_job(
        _run_async(cleanup),
        "interval",
        minutes=10,
        id="cache_cleanup",
        replace_existing=True,
    )

    # Content pipeline — previews, reviews, daily digest
    scheduler.add_job(
        _run_async(run_content_pipeline),
        "interval",
        minutes=30,
        id="content_pipeline",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started — ingestion every {settings.live_match_poll_interval}s, "
        f"live commentary every 30s"
    )


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
