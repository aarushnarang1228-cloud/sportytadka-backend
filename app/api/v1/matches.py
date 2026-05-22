"""
Match API endpoints — Multi-Sport.
All endpoints accept ?sport= filter. Defaults to showing all sports.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Match, MatchStatus
from app.schemas import MatchBrief, MatchDetail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/matches", tags=["matches"])


def _apply_sport_filter(query, sport: str | None):
    """Apply sport filter if provided."""
    if sport:
        query = query.where(Match.sport == sport)
    return query


@router.get("", response_model=list[MatchBrief])
async def list_matches(
    sport: str | None = Query(None, description="Filter: cricket, football, tennis, f1, nba"),
    status: str | None = Query(None, description="Filter: live, upcoming, completed"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Match)
        .order_by(desc(Match.priority), desc(Match.date))
        .limit(limit)
        .offset(offset)
    )
    query = _apply_sport_filter(query, sport)
    if status:
        try:
            query = query.where(Match.status == MatchStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    result = await db.execute(query)
    return [MatchBrief.model_validate(m) for m in result.scalars().all()]


@router.get("/live", response_model=list[MatchBrief])
async def get_live_matches(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"matches:live:{sport or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Match)
        .where(Match.status == MatchStatus.live)
        .order_by(desc(Match.priority), desc(Match.date))
    )
    query = _apply_sport_filter(query, sport)
    result = await db.execute(query)
    matches = [MatchBrief.model_validate(m) for m in result.scalars().all()]
    cache.set(cache_key, matches, ttl_seconds=15)
    return matches


@router.get("/upcoming", response_model=list[MatchBrief])
async def get_upcoming_matches(
    sport: str | None = Query(None),
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"matches:upcoming:{sport or 'all'}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Match)
        .where(Match.status == MatchStatus.upcoming)
        .order_by(desc(Match.priority), Match.date)
        .limit(limit)
    )
    query = _apply_sport_filter(query, sport)
    result = await db.execute(query)
    matches = [MatchBrief.model_validate(m) for m in result.scalars().all()]
    cache.set(cache_key, matches, ttl_seconds=120)
    return matches


@router.get("/recent", response_model=list[MatchBrief])
async def get_recent_matches(
    sport: str | None = Query(None),
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"matches:recent:{sport or 'all'}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Match)
        .where(Match.status == MatchStatus.completed)
        .order_by(desc(Match.priority), desc(Match.date))
        .limit(limit)
    )
    query = _apply_sport_filter(query, sport)
    result = await db.execute(query)
    matches = [MatchBrief.model_validate(m) for m in result.scalars().all()]
    cache.set(cache_key, matches, ttl_seconds=300)
    return matches


@router.get("/featured", response_model=list[MatchBrief])
async def get_featured_matches(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"matches:featured:{sport or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Live high-priority
    live_q = (
        select(Match)
        .where(Match.status == MatchStatus.live, Match.priority >= 30)
        .order_by(desc(Match.priority), desc(Match.date))
    )
    live_q = _apply_sport_filter(live_q, sport)
    live_result = await db.execute(live_q)
    featured = list(live_result.scalars().all())

    # Pad with recent completed
    if len(featured) < 8:
        remaining = 8 - len(featured)
        recent_q = (
            select(Match)
            .where(
                Match.status == MatchStatus.completed,
                or_(Match.priority >= 50, Match.ai_summary.isnot(None)),
            )
            .order_by(desc(Match.priority), desc(Match.date))
            .limit(remaining)
        )
        recent_q = _apply_sport_filter(recent_q, sport)
        recent_result = await db.execute(recent_q)
        featured.extend(recent_result.scalars().all())

    # Pad with upcoming
    if not featured:
        upcoming_q = (
            select(Match)
            .where(Match.status == MatchStatus.upcoming)
            .order_by(desc(Match.priority), Match.date)
            .limit(8)
        )
        upcoming_q = _apply_sport_filter(upcoming_q, sport)
        upcoming_result = await db.execute(upcoming_q)
        featured.extend(upcoming_result.scalars().all())

    matches = [MatchBrief.model_validate(m) for m in featured]
    cache.set(cache_key, matches, ttl_seconds=30)
    return matches


@router.get("/{slug}", response_model=MatchDetail)
async def get_match_detail(slug: str, db: AsyncSession = Depends(get_db)):
    cache_key = f"match:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        result = await db.execute(select(Match).where(Match.slug == slug))
        match = result.scalar_one_or_none()
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")

        detail = MatchDetail.model_validate(match)
        ttl = 20 if match.status == MatchStatus.live else 600
        cache.set(cache_key, detail, ttl_seconds=ttl)
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching match {slug}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading match: {str(e)}")
