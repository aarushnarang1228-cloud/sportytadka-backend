"""
Team API endpoints.

GET /teams            — list all teams
GET /teams/{slug}     — team detail with squad and fixtures
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Team, Match
from app.schemas import TeamBrief, TeamDetail, MatchBrief

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamBrief])
async def list_teams(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all teams."""
    cached = cache.get("teams:all")
    if cached is not None:
        return cached

    result = await db.execute(select(Team).order_by(Team.name).limit(limit))
    teams = [TeamBrief.model_validate(t) for t in result.scalars().all()]
    cache.set("teams:all", teams, ttl_seconds=600)
    return teams


@router.get("/{slug}", response_model=TeamDetail)
async def get_team_detail(slug: str, db: AsyncSession = Depends(get_db)):
    """Get team detail with full info."""
    cache_key = f"team:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(select(Team).where(Team.slug == slug))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    detail = TeamDetail.model_validate(team)
    cache.set(cache_key, detail, ttl_seconds=600)
    return detail


@router.get("/{slug}/fixtures", response_model=list[MatchBrief])
async def get_team_fixtures(
    slug: str,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get matches for a specific team."""
    # First get the team to find their name
    result = await db.execute(select(Team).where(Team.slug == slug))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Find matches where this team plays
    matches_result = await db.execute(
        select(Match)
        .where(
            or_(
                Match.team1_name.ilike(f"%{team.name}%"),
                Match.team2_name.ilike(f"%{team.name}%"),
            )
        )
        .order_by(desc(Match.date))
        .limit(limit)
    )
    return [MatchBrief.model_validate(m) for m in matches_result.scalars().all()]
