"""
Multi-sport data ingestion engine.

Runs as background tasks. Each sport has its own ingestion function.
All sports share the same Match/Team/Series models via the `sport` field.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db.session import async_session_factory
from app.models import Match, MatchFormat, MatchStatus, Team, Series, Sport
from app.services.cricket import get_cricket_provider
from app.services.football import get_football_provider
from app.services.f1 import get_f1_provider
from app.services.nba import get_nba_provider
from app.services.ai import get_ai_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:250]


async def _get_or_create_team(
    session: AsyncSession, name: str, sport: str = "cricket", short_name: str = ""
) -> Team | None:
    if not name or name == "TBD":
        return None
    external_id = f"{sport}_{_slugify(name)}"
    result = await session.execute(select(Team).where(Team.external_id == external_id))
    team = result.scalar_one_or_none()
    if team is None:
        team = Team(
            external_id=external_id,
            sport=sport,
            name=name,
            short_name=short_name or name[:3].upper(),
            slug=f"{sport}-{_slugify(name)}",
        )
        session.add(team)
        await session.flush()
    return team


async def _get_or_create_series(
    session: AsyncSession, name: str, sport: str = "cricket", priority: int = 10
) -> Series | None:
    if not name:
        return None
    slug = f"{sport}-{_slugify(name)}"
    result = await session.execute(select(Series).where(Series.slug == slug))
    series = result.scalar_one_or_none()
    if series is None:
        series = Series(
            sport=sport,
            name=name,
            slug=slug,
            priority=priority,
        )
        session.add(series)
        await session.flush()
    return series


# ---------------------------------------------------------------------------
# CRICKET ingestion (existing logic)
# ---------------------------------------------------------------------------

IPL_TEAMS = {
    "chennai super kings", "csk", "mumbai indians", "mi",
    "royal challengers", "rcb", "kolkata knight riders", "kkr",
    "delhi capitals", "dc", "sunrisers hyderabad", "srh",
    "rajasthan royals", "rr", "punjab kings", "pbks",
    "lucknow super giants", "lsg", "gujarat titans", "gt",
}
MAJOR_NATIONS = {
    "india", "australia", "england", "south africa", "new zealand",
    "pakistan", "sri lanka", "bangladesh", "west indies", "afghanistan",
}

def _cricket_priority(name: str, t1: str, t2: str) -> int:
    nl = name.lower(); t1l = t1.lower(); t2l = t2.lower()
    if any(k in nl for k in ["ipl", "indian premier league"]): return 100
    if any(t in t1l or t in t2l for t in IPL_TEAMS): return 100
    if any(k in nl for k in ["world cup", "champions trophy", "icc"]): return 90
    if "india" in t1l or "india" in t2l: return 80
    if any(k in nl for k in ["bbl", "psl", "cpl", "big bash", "the hundred", "sa20"]): return 70
    if t1l in MAJOR_NATIONS and t2l in MAJOR_NATIONS: return 60
    if t1l in MAJOR_NATIONS or t2l in MAJOR_NATIONS: return 50
    return 10

def _cricket_status(api_status, t1s, t2s, result):
    s = api_status.lower().strip()
    if s in ("abandoned", "no result", "cancelled"): return MatchStatus.abandoned
    result_lower = result.lower() if result else ""
    if any(w in result_lower for w in ["won", "drawn", "tied", "draw", "tie"]): return MatchStatus.completed
    if s in ("completed", "complete", "result", "match over"): return MatchStatus.completed
    if s in ("live", "in progress"): return MatchStatus.live
    if bool(t1s and t1s.strip()) or bool(t2s and t2s.strip()): return MatchStatus.live
    return MatchStatus.upcoming

def _extract_series(name):
    nl = name.lower()
    year_match = re.search(r"20[2-3]\d", name)
    year = year_match.group(0) if year_match else ""
    if "ipl" in nl: return f"IPL {year}" if year else "IPL"
    if "world cup" in nl:
        return f"ICC T20 World Cup {year}" if "t20" in nl else f"ICC Cricket World Cup {year}"
    parts = name.split(",")
    if len(parts) >= 2:
        teams = parts[0].strip()
        info = parts[1].strip().lower()
        for fmt_key, fmt_name in [("odi", "ODI"), ("t20i", "T20I"), ("t20", "T20"), ("test", "Test")]:
            if fmt_key in info:
                return f"{teams} {fmt_name} Series"
    return None

async def ingest_cricket() -> None:
    logger.info("Ingesting cricket matches...")
    provider = get_cricket_provider()
    try:
        live = await provider.get_live_matches()
        upcoming = await provider.get_upcoming_matches()
        recent = await provider.get_recent_matches()
        all_matches = live + upcoming + recent
        logger.info(f"Cricket: {len(all_matches)} matches fetched")
        if not all_matches: return

        async with async_session_factory() as session:
            for m in all_matches:
                if not m.external_id: continue
                ext_id = f"cricket_{m.external_id}"
                result = await session.execute(select(Match).where(Match.external_id == ext_id))
                db_match = result.scalar_one_or_none()

                status = _cricket_status(m.status, m.team1_score, m.team2_score, m.result)
                priority = _cricket_priority(m.name, m.team1_name, m.team2_name)
                team1 = await _get_or_create_team(session, m.team1_name, "cricket")
                team2 = await _get_or_create_team(session, m.team2_name, "cricket")
                series_name = _extract_series(m.name)
                series = await _get_or_create_series(session, series_name, "cricket", priority) if series_name else None

                if db_match is None:
                    db_match = Match(
                        external_id=ext_id, sport="cricket",
                        slug=f"cricket-{_slugify(f'{m.name}-{m.external_id[:8]}')}",
                        name=m.name, match_type=m.match_type, format=m.format or "other",
                        status=status, venue=m.venue, date=m.date, date_str=m.date_str,
                        team1_name=m.team1_name, team2_name=m.team2_name,
                        team1_id=team1.id if team1 else None, team2_id=team2.id if team2 else None,
                        team1_score=m.team1_score, team2_score=m.team2_score,
                        result=m.result, scorecard=m.scorecard,
                        priority=priority, is_featured=priority >= 50 and status == MatchStatus.live,
                        series_id=series.id if series else None, series_name=series_name,
                    )
                    session.add(db_match)
                else:
                    db_match.status = status
                    db_match.team1_score = m.team1_score or db_match.team1_score
                    db_match.team2_score = m.team2_score or db_match.team2_score
                    db_match.result = m.result or db_match.result
                    db_match.priority = max(priority, db_match.priority)
                    if m.scorecard: db_match.scorecard = m.scorecard

            await session.commit()
            logger.info(f"Cricket: upserted {len(all_matches)} matches")
    except Exception as e:
        logger.error(f"Cricket ingestion failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# FOOTBALL ingestion
# ---------------------------------------------------------------------------

async def ingest_football() -> None:
    logger.info("Ingesting football matches...")
    provider = get_football_provider()
    try:
        from app.services.football.provider import LEAGUES
        async with async_session_factory() as session:
            total = 0
            for code, info in LEAGUES.items():
                # Get recent + upcoming matches for this league
                try:
                    matches = await provider.get_matches(code)
                except Exception as e:
                    logger.warning(f"Football: failed to fetch {code}: {e}")
                    continue

                series = await _get_or_create_series(
                    session, info["name"], "football", info.get("priority", 50)
                )

                for m in matches[-20:]:  # Last 20 matches per league
                    result = await session.execute(
                        select(Match).where(Match.external_id == m.external_id)
                    )
                    db_match = result.scalar_one_or_none()

                    status = MatchStatus(m.status) if m.status in [e.value for e in MatchStatus] else MatchStatus.upcoming
                    team1 = await _get_or_create_team(session, m.team1_name, "football")
                    team2 = await _get_or_create_team(session, m.team2_name, "football")

                    if db_match is None:
                        db_match = Match(
                            external_id=m.external_id, sport="football",
                            slug=f"football-{_slugify(f'{m.name}-{m.external_id[-8:]}')}",
                            name=m.name, format="league", status=status,
                            venue=m.venue, date=m.date, date_str=m.date_str,
                            team1_name=m.team1_name, team2_name=m.team2_name,
                            team1_id=team1.id if team1 else None,
                            team2_id=team2.id if team2 else None,
                            team1_score=m.team1_score, team2_score=m.team2_score,
                            result=m.result, sport_data=m.sport_data,
                            priority=info.get("priority", 50),
                            series_id=series.id if series else None,
                            series_name=info["name"],
                        )
                        session.add(db_match)
                    else:
                        db_match.status = status
                        db_match.team1_score = m.team1_score or db_match.team1_score
                        db_match.team2_score = m.team2_score or db_match.team2_score
                        db_match.result = m.result or db_match.result
                        db_match.sport_data = m.sport_data

                    total += 1

            await session.commit()
            logger.info(f"Football: upserted {total} matches")
    except Exception as e:
        logger.error(f"Football ingestion failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# F1 ingestion
# ---------------------------------------------------------------------------

async def ingest_f1() -> None:
    logger.info("Ingesting F1 data...")
    provider = get_f1_provider()
    try:
        races = await provider.get_current_season_races()
        if not races: return

        async with async_session_factory() as session:
            series = await _get_or_create_series(session, "Formula 1 2026", "f1", 85)

            for race in races:
                result = await session.execute(
                    select(Match).where(Match.external_id == race.external_id)
                )
                db_match = result.scalar_one_or_none()
                status = MatchStatus(race.status) if race.status in [e.value for e in MatchStatus] else MatchStatus.upcoming

                if db_match is None:
                    db_match = Match(
                        external_id=race.external_id, sport="f1",
                        slug=f"f1-{_slugify(f'{race.name}-{race.round_number}')}",
                        name=race.name, format="race", status=status,
                        venue=race.circuit, date=race.date, date_str=race.date_str,
                        team1_name=race.country, team2_name=race.circuit,
                        sport_data=race.sport_data, priority=85,
                        series_id=series.id if series else None,
                        series_name="Formula 1 2026",
                    )
                    session.add(db_match)
                else:
                    db_match.status = status
                    db_match.sport_data = race.sport_data

            await session.commit()
            logger.info(f"F1: upserted {len(races)} races")
    except Exception as e:
        logger.error(f"F1 ingestion failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# NBA ingestion
# ---------------------------------------------------------------------------

async def ingest_nba() -> None:
    logger.info("Ingesting NBA data...")
    provider = get_nba_provider()
    try:
        recent = await provider.get_recent_games(5)
        upcoming = await provider.get_upcoming_games(5)
        games = recent + upcoming
        if not games:
            logger.info("NBA: no games found")
            return

        async with async_session_factory() as session:
            series = await _get_or_create_series(session, "NBA 2025-26", "nba", 75)

            for g in games:
                result = await session.execute(
                    select(Match).where(Match.external_id == g.external_id)
                )
                db_match = result.scalar_one_or_none()
                status = MatchStatus(g.status) if g.status in [e.value for e in MatchStatus] else MatchStatus.upcoming

                # Detect playoff games
                is_postseason = g.sport_data.get("postseason", False)
                fmt = "playoffs" if is_postseason else "regular_season"

                team1 = await _get_or_create_team(session, g.team1_name, "nba")
                team2 = await _get_or_create_team(session, g.team2_name, "nba")

                if db_match is None:
                    db_match = Match(
                        external_id=g.external_id, sport="nba",
                        slug=f"nba-{_slugify(f'{g.name}-{g.external_id[-8:]}')}",
                        name=g.name, format=fmt, status=status,
                        date=g.date, date_str=g.date_str,
                        team1_name=g.team1_name, team2_name=g.team2_name,
                        team1_id=team1.id if team1 else None,
                        team2_id=team2.id if team2 else None,
                        team1_score=g.team1_score, team2_score=g.team2_score,
                        result=g.result, sport_data=g.sport_data,
                        priority=85 if is_postseason else 75,
                        series_id=series.id if series else None,
                        series_name="NBA Playoffs 2026" if is_postseason else "NBA 2025-26",
                    )
                    session.add(db_match)
                else:
                    db_match.status = status
                    db_match.team1_score = g.team1_score or db_match.team1_score
                    db_match.team2_score = g.team2_score or db_match.team2_score
                    db_match.result = g.result or db_match.result
                    db_match.sport_data = g.sport_data

            await session.commit()
            logger.info(f"NBA: upserted {len(games)} games")
    except Exception as e:
        logger.error(f"NBA ingestion failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# TENNIS ingestion
# ---------------------------------------------------------------------------

async def ingest_tennis() -> None:
    logger.info("Ingesting tennis data...")
    from app.services.tennis import get_tennis_provider
    provider = get_tennis_provider()
    try:
        results = await provider.get_recent_results()
        tournaments = await provider.get_tournaments()
        if not results and not tournaments:
            logger.info("Tennis: no data")
            return

        async with async_session_factory() as session:
            # Create series entries for tournaments
            for t in tournaments:
                await _get_or_create_series(session, t["name"], "tennis", t.get("priority", 80))

            # Create match entries for recent results
            for m in results:
                result = await session.execute(
                    select(Match).where(Match.external_id == m.external_id)
                )
                db_match = result.scalar_one_or_none()

                series = await _get_or_create_series(session, m.tournament, "tennis", 90)

                if db_match is None:
                    db_match = Match(
                        external_id=m.external_id, sport="tennis",
                        slug=f"tennis-{_slugify(f'{m.name}-{m.external_id[-8:]}')}",
                        name=m.name, format="grand_slam" if "Open" in m.tournament or "Wimbledon" in m.tournament else "atp_1000",
                        status="completed",
                        date=m.date, date_str=m.date_str,
                        team1_name=m.team1_name, team2_name=m.team2_name,
                        team1_score=m.team1_score, team2_score=m.team2_score,
                        result=m.result, sport_data=m.sport_data,
                        priority=90, series_id=series.id if series else None,
                        series_name=m.tournament,
                    )
                    session.add(db_match)

            await session.commit()
            logger.info(f"Tennis: upserted {len(results)} matches, {len(tournaments)} tournaments")
    except Exception as e:
        logger.error(f"Tennis ingestion failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Master ingestion — runs all sports
# ---------------------------------------------------------------------------

async def ingest_matches() -> None:
    """Main ingestion job called by scheduler. Runs all sports."""
    await ingest_cricket()
    await ingest_football()
    await ingest_f1()
    await ingest_nba()
    await ingest_tennis()

    # Clear caches
    for sport in ["all", "cricket", "football", "f1", "nba", "tennis"]:
        cache.delete(f"matches:live:{sport}")
        cache.delete(f"matches:upcoming:{sport}:10")
        cache.delete(f"matches:recent:{sport}:10")
        cache.delete(f"matches:featured:{sport}")
    cache.delete("series:active")
