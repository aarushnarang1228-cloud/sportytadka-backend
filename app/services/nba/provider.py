"""
NBA data provider — balldontlie.io API.

Free tier requires API key (get from balldontlie.io).
Covers: games, teams, players, stats.
Handles regular season + playoffs + conference finals + NBA Finals.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class NBAGame:
    external_id: str
    name: str
    status: str
    season: int
    date: datetime | None = None
    date_str: str = ""
    team1_name: str = ""
    team2_name: str = ""
    team1_score: str = ""
    team2_score: str = ""
    result: str = ""
    sport_data: dict = field(default_factory=dict)


class NBAProvider:
    """Fetches NBA data from balldontlie.io v1 API."""

    def __init__(self):
        self.base_url = "https://api.balldontlie.io/v1"
        self.api_key = getattr(settings, "nba_api_key", "")

    async def _fetch(self, endpoint: str, params: dict = None) -> dict | None:
        if not self.api_key:
            logger.warning("NBA API key not configured — skipping NBA ingestion")
            return None
        try:
            headers = {"Authorization": self.api_key}
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}{endpoint}",
                    params=params or {},
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"NBA API {resp.status_code}: {endpoint}")
                return None
        except Exception as e:
            logger.error(f"NBA API error: {e}")
            return None

    def _parse_game(self, game: dict) -> NBAGame:
        home = game.get("home_team", {})
        visitor = game.get("visitor_team", {})

        home_name = home.get("full_name", "TBD")
        visitor_name = visitor.get("full_name", "TBD")
        home_score = game.get("home_team_score", 0)
        visitor_score = game.get("visitor_team_score", 0)

        # Determine status
        api_status = str(game.get("status", "")).strip()
        status = "upcoming"
        if api_status == "Final":
            status = "completed"
        elif api_status and api_status not in ("", "0:00", "12:00"):
            # Has a game clock value = live or completed
            if home_score > 0 or visitor_score > 0:
                status = "live" if "Q" in api_status or "Half" in api_status else "completed"

        # Result
        result = ""
        if status == "completed" and (home_score > 0 or visitor_score > 0):
            if home_score > visitor_score:
                result = f"{home_name} won {home_score}-{visitor_score}"
            elif visitor_score > home_score:
                result = f"{visitor_name} won {visitor_score}-{home_score}"
            else:
                result = f"Tied {home_score}-{visitor_score}"

        # Date — strip timezone for PostgreSQL
        dt = None
        date_str = game.get("date", "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                dt = dt.replace(tzinfo=None)
            except (ValueError, TypeError):
                try:
                    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

        return NBAGame(
            external_id=f"nba_{game.get('id', '')}",
            name=f"{visitor_name} @ {home_name}",
            status=status,
            season=game.get("season", 2025),
            date=dt,
            date_str=date_str[:10] if date_str else "",
            team1_name=home_name,
            team2_name=visitor_name,
            team1_score=str(home_score) if home_score else "",
            team2_score=str(visitor_score) if visitor_score else "",
            result=result,
            sport_data={
                "period": game.get("period"),
                "time": game.get("time"),
                "status": api_status,
                "postseason": game.get("postseason", False),
                "home_team_id": home.get("id"),
                "visitor_team_id": visitor.get("id"),
            },
        )

    async def get_games_for_dates(self, dates: list[str]) -> list[NBAGame]:
        """Get games for specific dates. dates = ['2026-05-20', '2026-05-19']."""
        all_games = []
        for d in dates:
            data = await self._fetch("/games", {"dates[]": d})
            if data:
                for g in data.get("data", []):
                    all_games.append(self._parse_game(g))
        return all_games

    async def get_todays_games(self) -> list[NBAGame]:
        """Get today's NBA games."""
        today = date.today().isoformat()
        return await self.get_games_for_dates([today])

    async def get_recent_games(self, days: int = 5) -> list[NBAGame]:
        """Get recent games including today."""
        dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(days)]
        return await self.get_games_for_dates(dates)

    async def get_upcoming_games(self, days: int = 5) -> list[NBAGame]:
        """Get upcoming games for the next few days."""
        dates = [(date.today() + timedelta(days=i)).isoformat() for i in range(1, days + 1)]
        return await self.get_games_for_dates(dates)

    async def get_teams(self) -> list[dict]:
        """Get all NBA teams."""
        data = await self._fetch("/teams")
        if not data:
            return []
        return [
            {
                "id": t.get("id"),
                "name": t.get("full_name"),
                "abbreviation": t.get("abbreviation"),
                "city": t.get("city"),
                "conference": t.get("conference"),
                "division": t.get("division"),
            }
            for t in data.get("data", [])
        ]


_provider: NBAProvider | None = None

def get_nba_provider() -> NBAProvider:
    global _provider
    if _provider is None:
        _provider = NBAProvider()
    return _provider
