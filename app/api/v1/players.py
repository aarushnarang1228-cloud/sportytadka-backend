"""
Player API endpoints.

GET /players           — list / search players
GET /players/{slug}    — player detail with career stats
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Player
from app.schemas import PlayerBrief, PlayerDetail

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerBrief])
async def list_players(
    search: str | None = Query(None, description="Search by name"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List or search players."""
    query = select(Player).order_by(Player.name).limit(limit).offset(offset)

    if search:
        query = query.where(Player.name.ilike(f"%{search}%"))

    result = await db.execute(query)
    return [PlayerBrief.model_validate(p) for p in result.scalars().all()]


@router.get("/{slug}", response_model=PlayerDetail)
async def get_player_detail(slug: str, db: AsyncSession = Depends(get_db)):
    """Get player detail with career stats."""
    cache_key = f"player:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(select(Player).where(Player.slug == slug))
    player = result.scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    detail = PlayerDetail.model_validate(player)
    cache.set(cache_key, detail, ttl_seconds=600)
    return detail
