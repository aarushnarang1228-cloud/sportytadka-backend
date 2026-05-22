"""
Pydantic schemas — Multi-Sport Platform.
Every schema now includes a sport field.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

class SeriesBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sport: str = "cricket"
    name: str
    short_name: str | None = None
    slug: str
    season: str | None = None
    series_type: str | None = None
    logo_url: str | None = None
    priority: int = 10


class SeriesDetail(SeriesBrief):
    start_date: datetime | None = None
    end_date: datetime | None = None
    country: str | None = None
    points_table: dict | None = None


class SeriesWithMatches(SeriesBrief):
    live_match: "MatchBrief | None" = None
    latest_result: "MatchBrief | None" = None
    match_count: int = 0


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class TeamBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sport: str = "cricket"
    name: str
    short_name: str | None = None
    slug: str
    logo_url: str | None = None


class TeamDetail(TeamBrief):
    country: str | None = None
    squad: dict | None = None


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class PlayerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sport: str = "cricket"
    name: str
    slug: str
    role: str | None = None
    image_url: str | None = None
    country: str | None = None
    position: str | None = None
    jersey_number: int | None = None
    constructor: str | None = None


class PlayerDetail(PlayerBrief):
    batting_style: str | None = None
    bowling_style: str | None = None
    date_of_birth: str | None = None
    nationality: str | None = None
    career_stats: dict | None = None
    team: TeamBrief | None = None


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

class MatchBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    sport: str = "cricket"
    slug: str
    name: str
    status: str
    format: str
    venue: str | None = None
    date: datetime | None = None
    date_str: str | None = None
    team1_name: str
    team2_name: str
    team1_score: str | None = None
    team2_score: str | None = None
    result: str | None = None
    ai_headline: str | None = None
    is_featured: bool = False
    priority: int = 10
    series_name: str | None = None
    sport_data: dict | None = None


class MatchDetail(MatchBrief):
    match_type: str | None = None
    scorecard: list | dict | None = None
    ai_summary: str | None = None
    ai_key_moments: list | None = None
    ai_generated_at: datetime | None = None
    series_id: int | None = None
    commentary: list | None = None


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------

class ArticleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sport: str = "cricket"
    slug: str
    title: str
    excerpt: str | None = None
    category: str
    published_at: datetime | None = None


class ArticleDetail(ArticleBrief):
    content: str
    tags: list | None = None
    match_id: int | None = None
    series_id: int | None = None


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    has_more: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
