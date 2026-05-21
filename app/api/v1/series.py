"""
Series / Tournament API endpoints.

GET /series              — list active series sorted by priority
GET /series/{slug}       — series detail with matches
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Series, Match, MatchStatus
from app.schemas import SeriesBrief, SeriesDetail, MatchBrief

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=list[SeriesBrief])
async def list_series(
    sport: str | None = Query(None, description="Filter: cricket, football, tennis, f1, nba"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """List series/tournaments sorted by priority. Cached 5 minutes."""
    cache_key = f"series:active:{sport or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Series)
        .order_by(desc(Series.priority), desc(Series.updated_at))
        .limit(limit)
    )
    if sport:
        query = query.where(Series.sport == sport)

    result = await db.execute(query)
    series_list = [SeriesBrief.model_validate(s) for s in result.scalars().all()]
    cache.set(cache_key, series_list, ttl_seconds=300)
    return series_list


@router.get("/{slug}", response_model=SeriesDetail)
async def get_series_detail(slug: str, db: AsyncSession = Depends(get_db)):
    """Full series detail. Cached 5 minutes."""
    cache_key = f"series:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(select(Series).where(Series.slug == slug))
    series = result.scalar_one_or_none()

    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    detail = SeriesDetail.model_validate(series)
    cache.set(cache_key, detail, ttl_seconds=300)
    return detail


@router.get("/{slug}/matches", response_model=list[MatchBrief])
async def get_series_matches(
    slug: str,
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get all matches in a series."""
    # First find the series
    series_result = await db.execute(select(Series).where(Series.slug == slug))
    series = series_result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    query = (
        select(Match)
        .where(Match.series_id == series.id)
        .order_by(desc(Match.date))
    )

    if status:
        try:
            status_enum = MatchStatus(status)
            query = query.where(Match.status == status_enum)
        except ValueError:
            pass

    result = await db.execute(query)
    return [MatchBrief.model_validate(m) for m in result.scalars().all()]
