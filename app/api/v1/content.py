"""
Content / Articles API endpoints — Week 2 enhancement.

GET /content/articles              — list published articles
GET /content/articles/latest       — latest articles (for homepage feed)
GET /content/articles/match/{id}   — articles for a specific match
GET /content/articles/{slug}       — article detail
GET /content/digest/latest         — latest daily digest
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db import get_db
from app.models import Article
from app.schemas import ArticleBrief, ArticleDetail

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/articles", response_model=list[ArticleBrief])
async def list_articles(
    category: str | None = Query(None, description="Filter: preview, review, digest, general"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List published articles with optional category filter."""
    query = (
        select(Article)
        .where(Article.is_published.is_(True))
        .order_by(desc(Article.published_at))
        .limit(limit)
        .offset(offset)
    )

    if category:
        query = query.where(Article.category == category)

    result = await db.execute(query)
    return [ArticleBrief.model_validate(a) for a in result.scalars().all()]


@router.get("/articles/latest", response_model=list[ArticleBrief])
async def get_latest_articles(
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Latest articles for homepage content feed. Cached 5 minutes."""
    cached = cache.get(f"articles:latest:{limit}")
    if cached is not None:
        return cached

    result = await db.execute(
        select(Article)
        .where(Article.is_published.is_(True))
        .order_by(desc(Article.published_at))
        .limit(limit)
    )
    articles = [ArticleBrief.model_validate(a) for a in result.scalars().all()]
    cache.set(f"articles:latest:{limit}", articles, ttl_seconds=300)
    return articles


@router.get("/articles/match/{match_id}", response_model=list[ArticleBrief])
async def get_match_articles(
    match_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all articles related to a specific match (preview + review)."""
    result = await db.execute(
        select(Article)
        .where(
            Article.match_id == match_id,
            Article.is_published.is_(True),
        )
        .order_by(desc(Article.published_at))
    )
    return [ArticleBrief.model_validate(a) for a in result.scalars().all()]


@router.get("/digest/latest", response_model=ArticleDetail | None)
async def get_latest_digest(db: AsyncSession = Depends(get_db)):
    """Get the latest daily digest. Cached 30 minutes."""
    cached = cache.get("digest:latest")
    if cached is not None:
        return cached

    result = await db.execute(
        select(Article)
        .where(
            Article.category == "digest",
            Article.is_published.is_(True),
        )
        .order_by(desc(Article.published_at))
        .limit(1)
    )
    article = result.scalar_one_or_none()
    if article is None:
        return None

    detail = ArticleDetail.model_validate(article)
    cache.set("digest:latest", detail, ttl_seconds=1800)
    return detail


@router.get("/articles/{slug}", response_model=ArticleDetail)
async def get_article_detail(slug: str, db: AsyncSession = Depends(get_db)):
    """Get article detail. Cached 5 minutes."""
    cache_key = f"article:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Article).where(Article.slug == slug, Article.is_published.is_(True))
    )
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    detail = ArticleDetail.model_validate(article)
    cache.set(cache_key, detail, ttl_seconds=300)
    return detail
