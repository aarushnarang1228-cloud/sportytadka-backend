"""
Live AI Commentary Engine.

Runs every 30 seconds. For each live match:
1. Compare current score with last known score in DB
2. If score changed → detect WHAT changed (runs, wicket, goal, set, etc.)
3. Generate sport-specific AI commentary for the change
4. Append to match.commentary JSON array
5. Frontend auto-refreshes to display new entries

Commentary format stored in match.commentary:
[
    {"time": "14:32", "text": "FOUR! Driven through covers...", "type": "boundary"},
    {"time": "14:35", "text": "WICKET! Clean bowled!", "type": "wicket"},
    ...
]
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.db.session import async_session_factory
from app.models import Match, MatchStatus
from app.services.ai import get_ai_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score change detection — sport-specific
# ---------------------------------------------------------------------------

def _detect_cricket_change(old_t1: str, old_t2: str, new_t1: str, new_t2: str) -> dict | None:
    """Detect what changed in a cricket score. Returns event info or None."""
    if old_t1 == new_t1 and old_t2 == new_t2:
        return None

    def parse_cricket_score(s):
        """Parse '186/5 (18.3 ov)' → (runs=186, wickets=5, overs='18.3')"""
        if not s or not s.strip():
            return {"runs": 0, "wickets": 0, "overs": "0"}
        try:
            parts = s.split("/")
            runs = int(parts[0].strip())
            rest = parts[1] if len(parts) > 1 else "0"
            wkt_str = rest.split("(")[0].strip()
            wickets = int(wkt_str) if wkt_str.isdigit() else 0
            overs = ""
            if "(" in rest:
                overs = rest.split("(")[1].replace("ov)", "").replace(")", "").strip()
            return {"runs": runs, "wickets": wickets, "overs": overs}
        except (ValueError, IndexError):
            return {"runs": 0, "wickets": 0, "overs": "0"}

    old1 = parse_cricket_score(old_t1)
    new1 = parse_cricket_score(new_t1)
    old2 = parse_cricket_score(old_t2)
    new2 = parse_cricket_score(new_t2)

    events = []

    # Check team 1 changes (currently batting)
    if new1["runs"] > old1["runs"]:
        run_diff = new1["runs"] - old1["runs"]
        if run_diff >= 6:
            events.append({"type": "boundary", "detail": f"SIX! {run_diff} runs added", "team": "team1"})
        elif run_diff >= 4:
            events.append({"type": "boundary", "detail": f"FOUR! {run_diff} runs added", "team": "team1"})
        else:
            events.append({"type": "runs", "detail": f"{run_diff} runs scored", "team": "team1"})

    if new1["wickets"] > old1["wickets"]:
        events.append({"type": "wicket", "detail": "WICKET FALLS!", "team": "team1"})

    # Check team 2 changes
    if new2["runs"] > old2["runs"]:
        run_diff = new2["runs"] - old2["runs"]
        if run_diff >= 6:
            events.append({"type": "boundary", "detail": f"SIX! {run_diff} runs added", "team": "team2"})
        elif run_diff >= 4:
            events.append({"type": "boundary", "detail": f"FOUR! {run_diff} runs added", "team": "team2"})
        else:
            events.append({"type": "runs", "detail": f"{run_diff} runs scored", "team": "team2"})

    if new2["wickets"] > old2["wickets"]:
        events.append({"type": "wicket", "detail": "WICKET FALLS!", "team": "team2"})

    # New innings started (team2 score appears for first time)
    if not old_t2 and new_t2 and new2["runs"] > 0:
        events.append({"type": "innings", "detail": "New innings started!", "team": "team2"})

    if events:
        return {
            "events": events,
            "score_t1": new_t1,
            "score_t2": new_t2,
        }
    return None


def _detect_football_change(old_t1: str, old_t2: str, new_t1: str, new_t2: str, sport_data: dict = None) -> dict | None:
    """Detect what changed in a football score."""
    if old_t1 == new_t1 and old_t2 == new_t2:
        # Score same — check if sport_data has new events (cards, substitutions)
        return None

    events = []
    try:
        old_home = int(old_t1) if old_t1 and old_t1.isdigit() else 0
        new_home = int(new_t1) if new_t1 and new_t1.isdigit() else 0
        old_away = int(old_t2) if old_t2 and old_t2.isdigit() else 0
        new_away = int(new_t2) if new_t2 and new_t2.isdigit() else 0

        if new_home > old_home:
            events.append({"type": "goal", "detail": f"GOAL! Home team scores! ({new_home}-{new_away})", "team": "team1"})
        if new_away > old_away:
            events.append({"type": "goal", "detail": f"GOAL! Away team scores! ({new_home}-{new_away})", "team": "team2"})
    except (ValueError, TypeError):
        return None

    if events:
        return {"events": events, "score_t1": new_t1, "score_t2": new_t2}
    return None


def _detect_nba_change(old_t1: str, old_t2: str, new_t1: str, new_t2: str, sport_data: dict = None) -> dict | None:
    """Detect significant changes in NBA score. Only generates for notable moments."""
    if old_t1 == new_t1 and old_t2 == new_t2:
        return None

    events = []
    try:
        old_home = int(old_t1) if old_t1 and old_t1.isdigit() else 0
        new_home = int(new_t1) if new_t1 and new_t1.isdigit() else 0
        old_away = int(old_t2) if old_t2 and old_t2.isdigit() else 0
        new_away = int(new_t2) if new_t2 and new_t2.isdigit() else 0

        home_diff = new_home - old_home
        away_diff = new_away - old_away
        margin = abs(new_home - new_away)
        total_score = new_home + new_away

        # Lead change — always notable
        if old_home > old_away and new_away > new_home:
            events.append({"type": "lead_change", "detail": f"LEAD CHANGE! Away team takes the lead! {new_home}-{new_away}", "team": "team2"})
        elif old_away > old_home and new_home > new_away:
            events.append({"type": "lead_change", "detail": f"LEAD CHANGE! Home team takes the lead! {new_home}-{new_away}", "team": "team1"})

        # Big scoring run (5+ points in one poll) — notable
        elif home_diff >= 5:
            events.append({"type": "score_run", "detail": f"Home team on a {home_diff}-0 run! {new_home}-{new_away}", "team": "team1"})
        elif away_diff >= 5:
            events.append({"type": "score_run", "detail": f"Away team on a {away_diff}-0 run! {new_home}-{new_away}", "team": "team2"})

        # Close game in crunch time (margin <= 5 and total score > 160 = late game)
        elif margin <= 5 and total_score > 160:
            leader = "Home" if new_home > new_away else "Away" if new_away > new_home else "Tied"
            events.append({"type": "score", "detail": f"CRUNCH TIME! {leader} leads {new_home}-{new_away}. Margin just {margin}!", "team": "team1"})

        # Skip routine 2-point baskets to avoid spamming

    except (ValueError, TypeError):
        return None

    if events:
        return {"events": events, "score_t1": new_t1, "score_t2": new_t2}
    return None


def detect_score_change(sport: str, old_t1: str, old_t2: str, new_t1: str, new_t2: str, sport_data: dict = None) -> dict | None:
    """Route to sport-specific change detection."""
    if sport == "cricket":
        return _detect_cricket_change(old_t1 or "", old_t2 or "", new_t1 or "", new_t2 or "")
    elif sport == "football":
        return _detect_football_change(old_t1 or "", old_t2 or "", new_t1 or "", new_t2 or "", sport_data)
    elif sport == "nba":
        return _detect_nba_change(old_t1 or "", old_t2 or "", new_t1 or "", new_t2 or "", sport_data)
    return None


# ---------------------------------------------------------------------------
# AI commentary generation — sport-aware prompts
# ---------------------------------------------------------------------------

COMMENTARY_PROMPTS = {
    "cricket": """You are a witty, exciting cricket commentator for SportyTadka.
Generate 1-2 sentences of live commentary for this moment.

Match: {match_name}
{team1} {score_t1} vs {team2} {score_t2}
What happened: {event_detail}

Be dramatic for wickets and sixes. Be descriptive for regular play.
Short, punchy, like a TV commentator. No hashtags, no emojis.""",

    "football": """You are an energetic football commentator for SportyTadka.
Generate 1-2 sentences of live commentary for this moment.

Match: {match_name}
{team1} {score_t1} - {team2} {score_t2}
What happened: {event_detail}

Be explosive for goals. Capture the drama. Think Martin Tyler "AGUEROOOO" energy.
Short, punchy. No hashtags, no emojis.""",

    "nba": """You are a hype NBA commentator for SportyTadka.
Generate 1-2 sentences of live commentary for this moment.

Match: {match_name}
{team1} {score_t1} - {team2} {score_t2}
What happened: {event_detail}

Be energetic for three-pointers and lead changes. Think "BANG!" energy.
Short, punchy. No hashtags, no emojis.""",
}


async def _generate_commentary_text(
    sport: str, match_name: str, team1: str, team2: str,
    score_t1: str, score_t2: str, event_detail: str
) -> str | None:
    """Generate AI commentary text for a score change event."""
    ai = get_ai_service()
    template = COMMENTARY_PROMPTS.get(sport)
    if not template:
        return None

    prompt = template.format(
        match_name=match_name, team1=team1, team2=team2,
        score_t1=score_t1, score_t2=score_t2, event_detail=event_detail,
    )

    try:
        text = await ai._generate_text(prompt)
        return text.strip() if text else None
    except Exception as e:
        logger.error(f"Commentary generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main live commentary job
# ---------------------------------------------------------------------------

async def update_live_commentary() -> None:
    """
    Runs every 30 seconds. Checks all live matches for score changes.
    Generates AI commentary for any changes detected.
    """
    try:
        async with async_session_factory() as session:
            # Get all live matches
            result = await session.execute(
                select(Match).where(Match.status == MatchStatus.live)
            )
            live_matches = result.scalars().all()

            if not live_matches:
                return

            logger.debug(f"Live commentary: checking {len(live_matches)} live matches")

            for match in live_matches:
                # Get cached previous scores
                cache_key = f"prev_score:{match.id}"
                prev = cache.get(cache_key)

                if prev is None:
                    # First time seeing this match live — store current scores, no commentary
                    cache.set(cache_key, {
                        "t1": match.team1_score or "",
                        "t2": match.team2_score or "",
                    }, ttl_seconds=7200)  # 2 hour TTL
                    continue

                # Detect changes
                change = detect_score_change(
                    sport=match.sport.value if hasattr(match.sport, 'value') else str(match.sport),
                    old_t1=prev.get("t1", ""),
                    old_t2=prev.get("t2", ""),
                    new_t1=match.team1_score or "",
                    new_t2=match.team2_score or "",
                    sport_data=match.sport_data,
                )

                if change is None:
                    continue  # No score change — skip AI call

                # Score changed! Generate commentary
                events = change.get("events", [])
                for event in events:
                    commentary_text = await _generate_commentary_text(
                        sport=match.sport.value if hasattr(match.sport, 'value') else str(match.sport),
                        match_name=match.name,
                        team1=match.team1_name,
                        team2=match.team2_name,
                        score_t1=change.get("score_t1", ""),
                        score_t2=change.get("score_t2", ""),
                        event_detail=event.get("detail", "Score update"),
                    )

                    if commentary_text:
                        # Append to commentary array
                        # CRITICAL: Must create a NEW list — SQLAlchemy won't detect
                        # in-place mutations to JSON columns
                        now = datetime.now(timezone.utc)
                        entry = {
                            "time": now.strftime("%H:%M"),
                            "timestamp": now.isoformat(),
                            "text": commentary_text,
                            "type": event.get("type", "update"),
                            "score": f"{match.team1_score} - {match.team2_score}",
                        }

                        existing = list(match.commentary or [])  # MUST copy
                        existing.append(entry)

                        # Keep only last 50 entries to avoid bloat
                        if len(existing) > 50:
                            existing = existing[-50:]

                        match.commentary = existing
                        logger.info(f"Commentary added: {match.name} — {event.get('type')}")

                # Update cached scores
                cache.set(cache_key, {
                    "t1": match.team1_score or "",
                    "t2": match.team2_score or "",
                }, ttl_seconds=7200)

            await session.commit()

    except Exception as e:
        logger.error(f"Live commentary update failed: {e}", exc_info=True)
