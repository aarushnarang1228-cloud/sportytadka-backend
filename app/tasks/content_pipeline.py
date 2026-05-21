"""
AI Content Pipeline — auto-generates articles.

Week 2: Background tasks that produce editorial content:
1. Match previews for upcoming high-priority matches
2. Match reviews for completed matches (richer than the basic summary)
3. Daily digest — "What happened in cricket today"

These run after match ingestion and create Article records.
"""

import logging
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db.session import async_session_factory
from app.models import Match, Article, MatchStatus, Series
from app.services.ai import get_ai_service

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:250]


async def generate_match_previews() -> None:
    """
    Generate preview articles for upcoming high-priority matches
    that don't already have a preview.
    """
    logger.info("Generating match previews...")
    ai = get_ai_service()

    try:
        async with async_session_factory() as session:
            # Find upcoming matches with priority >= 50 that lack a preview article
            matches_result = await session.execute(
                select(Match)
                .where(
                    Match.status == MatchStatus.upcoming,
                    Match.priority >= 50,
                )
                .order_by(desc(Match.priority), Match.date)
                .limit(5)
            )
            upcoming = matches_result.scalars().all()

            for match in upcoming:
                # Check if a preview already exists
                existing = await session.execute(
                    select(Article).where(
                        Article.match_id == match.id,
                        Article.category == "preview",
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                content = await ai.generate_match_preview(
                    match_name=match.name,
                    team1=match.team1_name,
                    team2=match.team2_name,
                    venue=match.venue or "",
                    format=match.format.value if match.format else "",
                    series_name=match.series_name or "",
                )

                if content:
                    slug = _slugify(f"preview-{match.name}-{match.id}")
                    title = f"Match Preview: {match.team1_name} vs {match.team2_name}"
                    article = Article(
                        slug=slug,
                        title=title,
                        content=content,
                        excerpt=content[:200] + "...",
                        category="preview",
                        tags=["preview", match.format.value if match.format else "cricket"],
                        match_id=match.id,
                        series_id=match.series_id,
                        is_published=True,
                        published_at=datetime.now(timezone.utc),
                    )
                    session.add(article)
                    logger.info(f"Generated preview for: {match.name}")

            await session.commit()

    except Exception as e:
        logger.error(f"Match preview generation failed: {e}", exc_info=True)


async def generate_match_reviews() -> None:
    """
    Generate detailed review articles for recently completed high-priority
    matches that don't already have a review.
    """
    logger.info("Generating match reviews...")
    ai = get_ai_service()

    try:
        async with async_session_factory() as session:
            # Find recently completed matches with priority >= 50
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            matches_result = await session.execute(
                select(Match)
                .where(
                    Match.status == MatchStatus.completed,
                    Match.priority >= 50,
                    Match.updated_at >= cutoff,
                )
                .order_by(desc(Match.priority))
                .limit(5)
            )
            completed = matches_result.scalars().all()

            for match in completed:
                # Check if a review already exists
                existing = await session.execute(
                    select(Article).where(
                        Article.match_id == match.id,
                        Article.category == "review",
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                content = await ai.generate_match_review(
                    match_name=match.name,
                    team1=match.team1_name,
                    team2=match.team2_name,
                    team1_score=match.team1_score or "",
                    team2_score=match.team2_score or "",
                    result=match.result or "",
                    venue=match.venue or "",
                    format=match.format.value if match.format else "",
                    scorecard=match.scorecard,
                )

                if content:
                    slug = _slugify(f"review-{match.name}-{match.id}")
                    title = f"Match Review: {match.team1_name} vs {match.team2_name}"
                    if match.result:
                        title = match.result[:100]

                    article = Article(
                        slug=slug,
                        title=title,
                        content=content,
                        excerpt=content[:200] + "...",
                        category="review",
                        tags=["review", match.format.value if match.format else "cricket"],
                        match_id=match.id,
                        series_id=match.series_id,
                        is_published=True,
                        published_at=datetime.now(timezone.utc),
                    )
                    session.add(article)
                    logger.info(f"Generated review for: {match.name}")

            await session.commit()

    except Exception as e:
        logger.error(f"Match review generation failed: {e}", exc_info=True)


async def generate_daily_digest() -> None:
    """
    Generate a daily "What happened in cricket today" digest article.
    Runs once per day.
    """
    logger.info("Generating daily digest...")
    ai = get_ai_service()

    try:
        async with async_session_factory() as session:
            today = datetime.now(timezone.utc).date()
            digest_slug = f"daily-digest-{today.isoformat()}"

            # Check if today's digest already exists
            existing = await session.execute(
                select(Article).where(Article.slug == digest_slug)
            )
            if existing.scalar_one_or_none():
                logger.info("Daily digest already exists for today")
                return

            # Get today's matches (completed + live)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            matches_result = await session.execute(
                select(Match)
                .where(
                    Match.status.in_([MatchStatus.completed, MatchStatus.live]),
                    Match.updated_at >= cutoff,
                )
                .order_by(desc(Match.priority), desc(Match.date))
                .limit(10)
            )
            matches = matches_result.scalars().all()

            if not matches:
                logger.info("No matches today for digest")
                return

            matches_data = [
                {
                    "name": m.name,
                    "team1_name": m.team1_name,
                    "team2_name": m.team2_name,
                    "team1_score": m.team1_score or "",
                    "team2_score": m.team2_score or "",
                    "result": m.result or "",
                    "status": m.status.value,
                }
                for m in matches
            ]

            content = await ai.generate_daily_digest(matches_data)

            if content:
                article = Article(
                    slug=digest_slug,
                    title=f"Cricket Daily Digest — {today.strftime('%B %d, %Y')}",
                    content=content,
                    excerpt=content[:200] + "...",
                    category="digest",
                    tags=["daily-digest", "cricket"],
                    is_published=True,
                    published_at=datetime.now(timezone.utc),
                )
                session.add(article)
                await session.commit()
                logger.info(f"Generated daily digest for {today}")

    except Exception as e:
        logger.error(f"Daily digest generation failed: {e}", exc_info=True)


async def run_content_pipeline() -> None:
    """Run all content generation tasks. Called by the scheduler."""
    await generate_match_previews()
    await generate_match_reviews()
    await generate_daily_digest()
    # Invalidate article cache
    cache.delete("articles:latest")
