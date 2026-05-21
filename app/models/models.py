"""
Database models for SportyTadka — Multi-Sport Platform.

Every entity has a `sport` field: cricket, football, tennis, f1, nba.
Match has `commentary` JSON field for live AI-generated commentary.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Sport(str, enum.Enum):
    cricket = "cricket"
    football = "football"
    tennis = "tennis"
    f1 = "f1"
    nba = "nba"


class MatchStatus(str, enum.Enum):
    upcoming = "upcoming"
    live = "live"
    completed = "completed"
    abandoned = "abandoned"


class MatchFormat(str, enum.Enum):
    t20 = "t20"; odi = "odi"; test = "test"; t20i = "t20i"
    league = "league"; cup = "cup"; friendly = "friendly"
    grand_slam = "grand_slam"; atp_1000 = "atp_1000"; atp_500 = "atp_500"; wta = "wta"
    race = "race"; qualifying = "qualifying"; sprint = "sprint"
    regular_season = "regular_season"; playoffs = "playoffs"
    other = "other"


class Series(Base):
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    sport: Mapped[Sport] = mapped_column(String(20), default=Sport.cricket, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    season: Mapped[str | None] = mapped_column(String(20), nullable=True)
    series_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    points_table: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    matches: Mapped[list["Match"]] = relationship(back_populates="series", lazy="selectin")
    __table_args__ = (Index("ix_series_sport_priority", "sport", "priority"),)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    sport: Mapped[Sport] = mapped_column(String(20), default=Sport.cricket, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(20), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    squad: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    players: Mapped[list["Player"]] = relationship(back_populates="team", lazy="selectin")


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    sport: Mapped[Sport] = mapped_column(String(20), default=Sport.cricket, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batting_style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bowling_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    constructor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teams.id"), nullable=True)
    career_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    team: Mapped[Team | None] = relationship(back_populates="players")


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    sport: Mapped[Sport] = mapped_column(String(20), default=Sport.cricket, index=True)
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    match_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    format: Mapped[MatchFormat] = mapped_column(String(20), default=MatchFormat.other)
    status: Mapped[MatchStatus] = mapped_column(String(20), default=MatchStatus.upcoming, index=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_str: Mapped[str | None] = mapped_column(String(50), nullable=True)
    series_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("series.id"), nullable=True)
    series_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    team1_name: Mapped[str] = mapped_column(String(200), nullable=False)
    team2_name: Mapped[str] = mapped_column(String(200), nullable=False)
    team1_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teams.id"), nullable=True)
    team2_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teams.id"), nullable=True)
    team1_score: Mapped[str | None] = mapped_column(String(100), nullable=True)
    team2_score: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sport_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scorecard: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # AI content
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_key_moments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Live AI commentary — array of {timestamp, text, event_type}
    # Updated every 30s during live matches when score changes
    commentary: Mapped[list | None] = mapped_column(JSON, nullable=True)

    priority: Mapped[int] = mapped_column(Integer, default=10)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    series: Mapped[Series | None] = relationship(back_populates="matches")

    __table_args__ = (
        Index("ix_matches_sport_status", "sport", "status"),
        Index("ix_matches_sport_priority", "sport", "priority", "date"),
        Index("ix_matches_status_date", "status", "date"),
        Index("ix_matches_featured", "is_featured", "date"),
        Index("ix_matches_series", "series_id", "date"),
    )


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport: Mapped[Sport] = mapped_column(String(20), default=Sport.cricket, index=True)
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    match_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("matches.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("series.id"), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
