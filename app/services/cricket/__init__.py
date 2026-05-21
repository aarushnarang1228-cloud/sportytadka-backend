"""
Cricket data service factory.

To switch providers, change the import and class below.
The rest of the codebase doesn't know or care which API is backing it.
"""

from app.services.cricket.provider import (
    CricketDataProvider,
    NormalizedMatch,
    NormalizedPlayer,
    NormalizedScorecard,
    NormalizedTeam,
)
from app.services.cricket.cricapi import CricAPIProvider

# The ONE place you change when swapping cricket data sources
_provider_instance: CricketDataProvider | None = None


def get_cricket_provider() -> CricketDataProvider:
    """Get the singleton cricket data provider."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = CricAPIProvider()
    return _provider_instance


__all__ = [
    "CricketDataProvider",
    "NormalizedMatch",
    "NormalizedPlayer",
    "NormalizedScorecard",
    "NormalizedTeam",
    "get_cricket_provider",
]
