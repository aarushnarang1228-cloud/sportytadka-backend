"""
Football data provider — football-data.org API.

Free tier: 10 requests/minute, covers:
- Premier League (PL)
- La Liga (PD)
- Bundesliga (BL1)
- Serie A (SA)
- Ligue 1 (FL1)
- Champions League (CL)
- FIFA World Cup (WC)
- European Championship (EC)

Sign up: https://www.football-data.org/client/register
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class FootballMatch:
    external_id: str
    name: str
    status: str  # SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, POSTPONED, CANCELLED
    competition: str
    competition_code: str
    matchday: int | None = None
    venue: str | None = None
    date: datetime | None = None
    date_str: str = ""
    team1_name: str = ""
    team2_name: str = ""
    team1_score: str = ""
    team2_score: str = ""
    result: str = ""
    team1_logo: str = ""
    team2_logo: str = ""
    sport_data: dict = field(default_factory=dict)


# Map football-data.org status → our status
STATUS_MAP = {
    "SCHEDULED": "upcoming",
    "TIMED": "upcoming",
    "IN_PLAY": "live",
    "PAUSED": "live",  # Halftime
    "FINISHED": "completed",
    "POSTPONED": "abandoned",
    "CANCELLED": "abandoned",
    "SUSPENDED": "abandoned",
    "AWARDED": "completed",
}

# Leagues we fetch (free tier)
LEAGUES = {
    "PL": {"name": "Premier League", "priority": 90, "country": "England"},
    "PD": {"name": "La Liga", "priority": 80, "country": "Spain"},
    "BL1": {"name": "Bundesliga", "priority": 75, "country": "Germany"},
    "SA": {"name": "Serie A", "priority": 75, "country": "Italy"},
    "FL1": {"name": "Ligue 1", "priority": 70, "country": "France"},
    "CL": {"name": "Champions League", "priority": 95, "country": "Europe"},
}


class FootballDataProvider:
    """Fetches football data from football-data.org."""

    def __init__(self):
        self.base_url = "https://api.football-data.org/v4"
        self.api_key = getattr(settings, "football_api_key", "")
        self.headers = {"X-Auth-Token": self.api_key} if self.api_key else {}

    async def _fetch(self, endpoint: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Football API {resp.status_code}: {endpoint}")
                return None
        except Exception as e:
            logger.error(f"Football API error: {e}")
            return None

    def _parse_match(self, match: dict, competition: str, comp_code: str) -> FootballMatch:
        home = match.get("homeTeam", {})
        away = match.get("awayTeam", {})
        score = match.get("score", {})
        full_time = score.get("fullTime", {})

        home_goals = full_time.get("home")
        away_goals = full_time.get("away")

        # For live matches, use current score
        if match.get("status") in ("IN_PLAY", "PAUSED"):
            half_time = score.get("halfTime", {})
            home_goals = full_time.get("home") or half_time.get("home") or 0
            away_goals = full_time.get("away") or half_time.get("away") or 0

        home_name = home.get("shortName") or home.get("name", "TBD")
        away_name = away.get("shortName") or away.get("name", "TBD")

        # Build result string
        result = ""
        api_status = match.get("status", "SCHEDULED")
        if api_status == "FINISHED" and home_goals is not None:
            if home_goals > away_goals:
                result = f"{home_name} won {home_goals}-{away_goals}"
            elif away_goals > home_goals:
                result = f"{away_name} won {away_goals}-{home_goals}"
            else:
                result = f"Draw {home_goals}-{away_goals}"

        # Parse date — strip timezone for PostgreSQL TIMESTAMP WITHOUT TIME ZONE
        utc_date = match.get("utcDate", "")
        dt = None
        if utc_date:
            try:
                dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
                dt = dt.replace(tzinfo=None)  # Strip timezone
            except (ValueError, TypeError):
                pass

        # Sport-specific data
        sport_data = {
            "matchday": match.get("matchday"),
            "stage": match.get("stage"),
            "group": match.get("group"),
            "minute": match.get("minute"),
            "half_time": score.get("halfTime"),
            "full_time": full_time,
            "referees": [r.get("name") for r in match.get("referees", [])],
        }

        return FootballMatch(
            external_id=f"fb_{match.get('id', '')}",
            name=f"{home_name} vs {away_name}",
            status=STATUS_MAP.get(api_status, "upcoming"),
            competition=competition,
            competition_code=comp_code,
            matchday=match.get("matchday"),
            venue=match.get("venue"),
            date=dt,
            date_str=utc_date[:10] if utc_date else "",
            team1_name=home_name,
            team2_name=away_name,
            team1_score=str(home_goals) if home_goals is not None else "",
            team2_score=str(away_goals) if away_goals is not None else "",
            result=result,
            team1_logo=home.get("crest", ""),
            team2_logo=away.get("crest", ""),
            sport_data=sport_data,
        )

    async def get_matches(self, league_code: str = "PL", status: str = "") -> list[FootballMatch]:
        """Get matches for a league. Status: SCHEDULED, LIVE, FINISHED."""
        endpoint = f"/competitions/{league_code}/matches"
        if status:
            endpoint += f"?status={status}"
        data = await self._fetch(endpoint)
        if not data:
            return []

        league_info = LEAGUES.get(league_code, {"name": league_code})
        matches = []
        for m in data.get("matches", []):
            matches.append(self._parse_match(m, league_info["name"], league_code))
        return matches

    async def get_live_matches(self) -> list[FootballMatch]:
        """Get all live football matches across all leagues."""
        all_live = []
        for code in LEAGUES:
            matches = await self.get_matches(code, "LIVE")
            all_live.extend(matches)
        return all_live

    async def get_upcoming_matches(self) -> list[FootballMatch]:
        """Get upcoming matches across all leagues."""
        all_upcoming = []
        for code in LEAGUES:
            matches = await self.get_matches(code, "SCHEDULED")
            all_upcoming.extend(matches[:5])  # Limit per league to save API calls
        return all_upcoming

    async def get_recent_matches(self) -> list[FootballMatch]:
        """Get recently finished matches."""
        all_recent = []
        for code in LEAGUES:
            matches = await self.get_matches(code, "FINISHED")
            all_recent.extend(matches[-5:])  # Last 5 per league
        return all_recent

    async def get_standings(self, league_code: str = "PL") -> dict | None:
        """Get league standings."""
        data = await self._fetch(f"/competitions/{league_code}/standings")
        if not data:
            return None

        standings = data.get("standings", [])
        if not standings:
            return None

        # Parse the total standings (first group)
        table = standings[0].get("table", [])
        teams = []
        for entry in table:
            team = entry.get("team", {})
            teams.append({
                "position": entry.get("position"),
                "name": team.get("shortName") or team.get("name"),
                "played": entry.get("playedGames"),
                "won": entry.get("won"),
                "drawn": entry.get("draw"),
                "lost": entry.get("lost"),
                "goals_for": entry.get("goalsFor"),
                "goals_against": entry.get("goalsAgainst"),
                "goal_difference": entry.get("goalDifference"),
                "points": entry.get("points"),
                "form": entry.get("form"),
                "crest": team.get("crest"),
            })
        return {"teams": teams, "league": LEAGUES.get(league_code, {}).get("name", league_code)}

    async def get_top_scorers(self, league_code: str = "PL") -> list[dict]:
        """Get top scorers for a league."""
        data = await self._fetch(f"/competitions/{league_code}/scorers?limit=20")
        if not data:
            return []

        scorers = []
        for entry in data.get("scorers", []):
            player = entry.get("player", {})
            team = entry.get("team", {})
            scorers.append({
                "name": player.get("name"),
                "nationality": player.get("nationality"),
                "team": team.get("shortName") or team.get("name"),
                "goals": entry.get("goals", 0),
                "assists": entry.get("assists", 0),
                "penalties": entry.get("penalties", 0),
                "played": entry.get("playedMatches", 0),
            })
        return scorers


# Singleton
_provider: FootballDataProvider | None = None


def get_football_provider() -> FootballDataProvider:
    global _provider
    if _provider is None:
        _provider = FootballDataProvider()
    return _provider
