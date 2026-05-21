"""
SEO helper endpoints — provides data for sitemap, structured data.

GET /seo/sitemap-data  — returns all slugs + dates for sitemap.xml generation
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.cache import cache
from app.db import get_db
from app.models import Match, Series, Team, Article

router = APIRouter(prefix="/seo", tags=["seo"])


class SitemapEntry(BaseModel):
    loc: str
    lastmod: str | None = None
    priority: float = 0.5
    changefreq: str = "daily"


class SitemapData(BaseModel):
    matches: list[SitemapEntry]
    series: list[SitemapEntry]
    teams: list[SitemapEntry]
    articles: list[SitemapEntry]


@router.get("/sitemap-data", response_model=SitemapData)
async def get_sitemap_data(db: AsyncSession = Depends(get_db)):
    """Return all slugs + metadata for dynamic sitemap generation. Cached 1 hour."""
    cached = cache.get("seo:sitemap")
    if cached is not None:
        return cached

    # Matches
    matches_result = await db.execute(
        select(Match.slug, Match.updated_at, Match.status, Match.priority)
        .order_by(desc(Match.priority), desc(Match.updated_at))
        .limit(500)
    )
    matches = []
    for row in matches_result:
        freq = "hourly" if row.status == "live" else "daily" if row.status == "upcoming" else "weekly"
        prio = 0.9 if row.priority >= 80 else 0.7 if row.priority >= 50 else 0.5
        matches.append(SitemapEntry(
            loc=f"/match/{row.slug}",
            lastmod=row.updated_at.isoformat() if row.updated_at else None,
            priority=prio,
            changefreq=freq,
        ))

    # Series
    series_result = await db.execute(
        select(Series.slug, Series.updated_at, Series.priority)
        .order_by(desc(Series.priority))
        .limit(100)
    )
    series = []
    for row in series_result:
        prio = 0.9 if row.priority >= 80 else 0.7
        series.append(SitemapEntry(
            loc=f"/series/{row.slug}",
            lastmod=row.updated_at.isoformat() if row.updated_at else None,
            priority=prio,
            changefreq="daily",
        ))

    # Teams
    teams_result = await db.execute(
        select(Team.slug, Team.updated_at)
        .order_by(desc(Team.updated_at))
        .limit(200)
    )
    teams = [
        SitemapEntry(
            loc=f"/team/{row.slug}",
            lastmod=row.updated_at.isoformat() if row.updated_at else None,
            priority=0.6,
            changefreq="weekly",
        )
        for row in teams_result
    ]

    # Articles
    articles_result = await db.execute(
        select(Article.slug, Article.published_at)
        .where(Article.is_published.is_(True))
        .order_by(desc(Article.published_at))
        .limit(200)
    )
    articles = [
        SitemapEntry(
            loc=f"/article/{row.slug}",
            lastmod=row.published_at.isoformat() if row.published_at else None,
            priority=0.6,
            changefreq="weekly",
        )
        for row in articles_result
    ]

    data = SitemapData(
        matches=matches,
        series=series,
        teams=teams,
        articles=articles,
    )
    cache.set("seo:sitemap", data, ttl_seconds=3600)
    return data
