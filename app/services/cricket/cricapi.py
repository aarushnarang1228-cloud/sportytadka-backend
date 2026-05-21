"""
CricAPI v1 implementation.

API docs: https://cricapi.com/
Free tier: 100 requests/day — enough for MVP if we cache aggressively.

IMPORTANT: CricAPI response shapes can vary. This implementation handles
missing fields gracefully with .get() defaults everywhere. If CricAPI changes
their response format, only THIS file needs updating.
"""

import logging
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.services.cricket.provider import (
    CricketDataProvider,
    NormalizedMatch,
    NormalizedPlayer,
    NormalizedScorecard,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _parse_status(status_str: str) -> str:
    """Map CricAPI status strings to our normalized statuses."""
    s = status_str.lower().strip()
    if s in ("live", "in progress"):
        return "live"
    if s in ("upcoming", "not started", "scheduled"):
        return "upcoming"
    if s in ("completed", "complete", "result"):
        return "completed"
    if s in ("abandoned", "no result", "cancelled"):
        return "abandoned"
    return "upcoming"


def _parse_format(match_type: str) -> str:
    """Map CricAPI match type to our format enum."""
    t = match_type.lower().strip()
    if "t20i" in t:
        return "t20i"
    if "t20" in t:
        return "t20"
    if "odi" in t:
        return "odi"
    if "test" in t:
        return "test"
    return "other"


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse CricAPI date strings into datetime."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _normalize_match(data: dict) -> NormalizedMatch:
    """Convert a CricAPI match object to our normalized format."""
    teams = data.get("teams", [])
    team_info = data.get("teamInfo", [])

    team1_name = teams[0] if len(teams) > 0 else "TBD"
    team2_name = teams[1] if len(teams) > 1 else "TBD"
    team1_id = team_info[0].get("shortname", "") if len(team_info) > 0 else ""
    team2_id = team_info[1].get("shortname", "") if len(team_info) > 1 else ""

    # Score extraction
    score = data.get("score", [])
    team1_score = ""
    team2_score = ""
    if score:
        # CricAPI returns score as a list of innings
        for s in score:
            inning_str = s.get("inning", "")
            score_str = f"{s.get('r', '')}/{s.get('w', '')} ({s.get('o', '')} ov)"
            if team1_name.lower() in inning_str.lower():
                team1_score = score_str if not team1_score else team1_score
            elif team2_name.lower() in inning_str.lower():
                team2_score = score_str if not team2_score else team2_score

    return NormalizedMatch(
        external_id=data.get("id", ""),
        name=data.get("name", "Unknown Match"),
        status=_parse_status(data.get("status", "upcoming")),
        match_type=data.get("matchType", ""),
        format=_parse_format(data.get("matchType", "")),
        venue=data.get("venue", ""),
        date=_parse_date(data.get("date", "") or data.get("dateTimeGMT", "")),
        date_str=data.get("date", ""),
        team1_name=team1_name,
        team2_name=team2_name,
        team1_id=team1_id,
        team2_id=team2_id,
        team1_score=team1_score,
        team2_score=team2_score,
        result=data.get("status", ""),
        scorecard=data.get("score"),
    )


class CricAPIProvider(CricketDataProvider):
    """CricAPI v1 implementation."""

    def __init__(self) -> None:
        self.base_url = settings.cricket_api_base_url
        self.api_key = settings.cricket_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make an authenticated request to CricAPI."""
        client = await self._get_client()
        url = f"{self.base_url}/{endpoint}"
        request_params = {"apikey": self.api_key}
        if params:
            request_params.update(params)

        try:
            response = await client.get(url, params=request_params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.warning(f"CricAPI returned non-success: {data.get('status')}")
                return {"data": []}

            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"CricAPI HTTP error: {e.response.status_code} for {endpoint}")
            return {"data": []}
        except httpx.RequestError as e:
            logger.error(f"CricAPI request error: {e}")
            return {"data": []}
        except Exception as e:
            logger.error(f"CricAPI unexpected error: {e}")
            return {"data": []}

    async def get_live_matches(self) -> list[NormalizedMatch]:
        data = await self._request("currentMatches")
        matches = data.get("data", [])
        if not isinstance(matches, list):
            return []
        return [
            _normalize_match(m) for m in matches
            if _parse_status(m.get("status", "")) == "live"
        ]

    async def get_upcoming_matches(self) -> list[NormalizedMatch]:
        data = await self._request("currentMatches")
        matches = data.get("data", [])
        if not isinstance(matches, list):
            return []
        return [
            _normalize_match(m) for m in matches
            if _parse_status(m.get("status", "")) == "upcoming"
        ]

    async def get_recent_matches(self) -> list[NormalizedMatch]:
        data = await self._request("currentMatches")
        matches = data.get("data", [])
        if not isinstance(matches, list):
            return []
        return [
            _normalize_match(m) for m in matches
            if _parse_status(m.get("status", "")) == "completed"
        ]

    async def get_match_scorecard(self, match_external_id: str) -> NormalizedScorecard | None:
        data = await self._request("match_scorecard", {"id": match_external_id})
        match_data = data.get("data", {})
        if not match_data:
            return None

        scorecard_data = match_data.get("scorecard", []) if isinstance(match_data, dict) else []

        return NormalizedScorecard(
            match_external_id=match_external_id,
            innings=scorecard_data if isinstance(scorecard_data, list) else [],
        )

    async def get_match_info(self, match_external_id: str) -> NormalizedMatch | None:
        data = await self._request("match_info", {"id": match_external_id})
        match_data = data.get("data", {})
        if not match_data or not isinstance(match_data, dict):
            return None
        return _normalize_match(match_data)

    async def search_players(self, query: str) -> list[NormalizedPlayer]:
        data = await self._request("players", {"search": query})
        players = data.get("data", [])
        if not isinstance(players, list):
            return []
        return [
            NormalizedPlayer(
                external_id=p.get("id", ""),
                name=p.get("name", "Unknown"),
                country=p.get("country", ""),
            )
            for p in players
        ]

    async def get_player_info(self, player_external_id: str) -> NormalizedPlayer | None:
        data = await self._request("players_info", {"id": player_external_id})
        p = data.get("data", {})
        if not p or not isinstance(p, dict):
            return None
        return NormalizedPlayer(
            external_id=p.get("id", ""),
            name=p.get("name", "Unknown"),
            country=p.get("country", ""),
            image_url=p.get("playerImg", ""),
            role=p.get("role", ""),
            batting_style=p.get("battingStyle", ""),
            bowling_style=p.get("bowlingStyle", ""),
            date_of_birth=p.get("dateOfBirth", ""),
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
