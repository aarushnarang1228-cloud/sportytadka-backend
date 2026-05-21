"""
Global search endpoint.

GET /search?q=india&limit=10  — search across matches, teams, series, articles

Uses SQL LIKE for simplicity. Works on both SQLite and PostgreSQL.
For production scale, replace with full-text search (pg_trgm or Meilisearch).
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Match, Team, Series, Article

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    type: str  # "match", "team", "series", "article"
    id: int
    name: str
    slug: str
    subtitle: str | None = None
    priority: int = 0


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=2, max_length=100, description="Search query"),
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Search across matches, teams, series, and articles.
    Returns unified results sorted by relevance (priority).
    Cached 60 seconds per query.
    """
    q_clean = q.strip().lower()
    cache_key = f"search:{q_clean}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    pattern = f"%{q_clean}%"
    results: list[SearchResult] = []

    # Search matches
    match_result = await db.execute(
        select(Match)
        .where(
            or_(
                func.lower(Match.name).like(pattern),
                func.lower(Match.team1_name).like(pattern),
                func.lower(Match.team2_name).like(pattern),
                func.lower(Match.series_name).like(pattern),
                func.lower(Match.result).like(pattern),
            )
        )
        .order_by(desc(Match.priority), desc(Match.date))
        .limit(limit)
    )
    for m in match_result.scalars():
        subtitle = m.result or f"{m.team1_name} vs {m.team2_name}"
        if m.series_name:
            subtitle = f"{m.series_name} • {subtitle}"
        results.append(SearchResult(
            type="match",
            id=m.id,
            name=m.name,
            slug=m.slug,
            subtitle=subtitle[:100],
            priority=m.priority + (20 if m.status.value == "live" else 0),
        ))

    # Search teams
    team_result = await db.execute(
        select(Team)
        .where(
            or_(
                func.lower(Team.name).like(pattern),
                func.lower(Team.short_name).like(pattern),
            )
        )
        .limit(10)
    )
    for t in team_result.scalars():
        results.append(SearchResult(
            type="team",
            id=t.id,
            name=t.name,
            slug=t.slug,
            subtitle=t.country or t.short_name,
            priority=40,
        ))

    # Search series
    series_result = await db.execute(
        select(Series)
        .where(
            or_(
                func.lower(Series.name).like(pattern),
                func.lower(Series.short_name).like(pattern),
            )
        )
        .order_by(desc(Series.priority))
        .limit(10)
    )
    for s in series_result.scalars():
        results.append(SearchResult(
            type="series",
            id=s.id,
            name=s.name,
            slug=s.slug,
            subtitle=s.season or s.series_type,
            priority=s.priority,
        ))

    # Search articles
    article_result = await db.execute(
        select(Article)
        .where(
            Article.is_published.is_(True),
            or_(
                func.lower(Article.title).like(pattern),
                func.lower(Article.excerpt).like(pattern),
            ),
        )
        .order_by(desc(Article.published_at))
        .limit(5)
    )
    for a in article_result.scalars():
        results.append(SearchResult(
            type="article",
            id=a.id,
            name=a.title,
            slug=a.slug,
            subtitle=a.category.title(),
            priority=30,
        ))

    # Sort by priority desc, take top N
    results.sort(key=lambda r: r.priority, reverse=True)
    results = results[:limit]

    response = SearchResponse(query=q, results=results, total=len(results))
    cache.set(cache_key, response, ttl_seconds=60)
    return response
