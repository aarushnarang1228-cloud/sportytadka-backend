"""
Cricket data provider interface.

This is the most important abstraction in the codebase. Every cricket API
(CricAPI, SportRadar, custom scraper) implements this interface. The rest
of the app only talks to the interface, never to a specific API.

When you need to switch providers:
1. Create a new class implementing CricketDataProvider
2. Change one line in the factory function
3. Everything else works unchanged
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Normalized data structures
# ---------------------------------------------------------------------------
# These are what the rest of the app works with, regardless of which API
# provided the raw data. Every provider must map its response to these.

@dataclass
class NormalizedTeam:
    external_id: str
    name: str
    short_name: str = ""
    logo_url: str = ""
    country: str = ""


@dataclass
class NormalizedPlayer:
    external_id: str
    name: str
    country: str = ""
    image_url: str = ""
    role: str = ""
    batting_style: str = ""
    bowling_style: str = ""
    date_of_birth: str = ""
    team_external_id: str = ""


@dataclass
class NormalizedMatch:
    external_id: str
    name: str
    status: str  # "upcoming", "live", "completed", "abandoned"
    match_type: str = ""
    format: str = "other"  # "t20", "odi", "test", "t20i", "other"
    venue: str = ""
    date: datetime | None = None
    date_str: str = ""
    team1_name: str = ""
    team2_name: str = ""
    team1_id: str = ""
    team2_id: str = ""
    team1_score: str = ""
    team2_score: str = ""
    result: str = ""
    scorecard: dict | None = None


@dataclass
class NormalizedScorecard:
    match_external_id: str
    innings: list[dict] = field(default_factory=list)
    # Each innings dict: {"team": str, "score": str, "overs": str,
    #                     "batting": [...], "bowling": [...]}


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class CricketDataProvider(ABC):
    """
    Abstract interface for cricket data sources.
    Every method returns normalized data structures, never raw API responses.
    """

    @abstractmethod
    async def get_live_matches(self) -> list[NormalizedMatch]:
        """Fetch currently live matches."""
        ...

    @abstractmethod
    async def get_upcoming_matches(self) -> list[NormalizedMatch]:
        """Fetch upcoming/scheduled matches."""
        ...

    @abstractmethod
    async def get_recent_matches(self) -> list[NormalizedMatch]:
        """Fetch recently completed matches."""
        ...

    @abstractmethod
    async def get_match_scorecard(self, match_external_id: str) -> NormalizedScorecard | None:
        """Fetch detailed scorecard for a specific match."""
        ...

    @abstractmethod
    async def get_match_info(self, match_external_id: str) -> NormalizedMatch | None:
        """Fetch full info for a specific match."""
        ...

    @abstractmethod
    async def search_players(self, query: str) -> list[NormalizedPlayer]:
        """Search for players by name."""
        ...

    @abstractmethod
    async def get_player_info(self, player_external_id: str) -> NormalizedPlayer | None:
        """Fetch detailed player info."""
        ...
