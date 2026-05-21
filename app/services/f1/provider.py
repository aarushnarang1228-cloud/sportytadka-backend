"""
F1 data provider — Jolpica API (free, open-source).
Replacement for the deprecated Ergast API.
Covers all F1 seasons, races, drivers, constructors, standings.
API: https://api.jolpi.ca/ergast/
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class F1Race:
    external_id: str
    name: str
    status: str
    circuit: str
    country: str
    date: datetime | None = None
    date_str: str = ""
    round_number: int = 0
    results: list = field(default_factory=list)
    sport_data: dict = field(default_factory=dict)


class F1Provider:
    """Fetches F1 data from Jolpica API."""

    def __init__(self):
        self.base_url = "https://api.jolpi.ca/ergast/f1"

    async def _fetch(self, endpoint: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}{endpoint}.json")
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"F1 API {resp.status_code}: {endpoint}")
                return None
        except Exception as e:
            logger.error(f"F1 API error: {e}")
            return None

    async def get_current_season_races(self) -> list[F1Race]:
        """Get all races in the current season."""
        data = await self._fetch("/current")
        if not data:
            return []

        races = []
        race_table = data.get("MRData", {}).get("RaceTable", {})
        for race in race_table.get("Races", []):
            circuit = race.get("Circuit", {})
            location = circuit.get("Location", {})

            dt = None
            date_str = race.get("date", "")
            time_str = race.get("time", "")
            if date_str:
                try:
                    dt_str = f"{date_str}T{time_str}" if time_str else date_str
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    dt = dt.replace(tzinfo=None)  # Strip timezone
                except (ValueError, TypeError):
                    pass

            # Determine status based on date
            now = datetime.utcnow()
            status = "upcoming"
            if dt and dt < now:
                status = "completed"

            races.append(F1Race(
                external_id=f"f1_{race.get('season', '')}_{race.get('round', '')}",
                name=race.get("raceName", ""),
                status=status,
                circuit=circuit.get("circuitName", ""),
                country=location.get("country", ""),
                date=dt,
                date_str=date_str,
                round_number=int(race.get("round", 0)),
                sport_data={
                    "season": race.get("season"),
                    "round": race.get("round"),
                    "circuit_id": circuit.get("circuitId"),
                    "locality": location.get("locality"),
                    "lat": location.get("lat"),
                    "long": location.get("long"),
                },
            ))
        return races

    async def get_driver_standings(self) -> list[dict]:
        """Get current driver standings."""
        data = await self._fetch("/current/driverStandings")
        if not data:
            return []

        standings_table = data.get("MRData", {}).get("StandingsTable", {})
        standings_lists = standings_table.get("StandingsLists", [])
        if not standings_lists:
            return []

        drivers = []
        for entry in standings_lists[0].get("DriverStandings", []):
            driver = entry.get("Driver", {})
            constructors = entry.get("Constructors", [])
            constructor_name = constructors[0].get("name", "") if constructors else ""

            drivers.append({
                "position": int(entry.get("position", 0)),
                "name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}",
                "code": driver.get("code", ""),
                "nationality": driver.get("nationality", ""),
                "constructor": constructor_name,
                "points": float(entry.get("points", 0)),
                "wins": int(entry.get("wins", 0)),
            })
        return drivers

    async def get_constructor_standings(self) -> list[dict]:
        """Get current constructor standings."""
        data = await self._fetch("/current/constructorStandings")
        if not data:
            return []

        standings_table = data.get("MRData", {}).get("StandingsTable", {})
        standings_lists = standings_table.get("StandingsLists", [])
        if not standings_lists:
            return []

        constructors = []
        for entry in standings_lists[0].get("ConstructorStandings", []):
            constructor = entry.get("Constructor", {})
            constructors.append({
                "position": int(entry.get("position", 0)),
                "name": constructor.get("name", ""),
                "nationality": constructor.get("nationality", ""),
                "points": float(entry.get("points", 0)),
                "wins": int(entry.get("wins", 0)),
            })
        return constructors

    async def get_race_results(self, round_num: int = 0) -> list[dict]:
        """Get results for a specific race. 0 = latest."""
        endpoint = "/current/last/results" if round_num == 0 else f"/current/{round_num}/results"
        data = await self._fetch(endpoint)
        if not data:
            return []

        race_table = data.get("MRData", {}).get("RaceTable", {})
        races = race_table.get("Races", [])
        if not races:
            return []

        results = []
        for entry in races[0].get("Results", []):
            driver = entry.get("Driver", {})
            constructor = entry.get("Constructor", {})
            results.append({
                "position": entry.get("position"),
                "name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}",
                "code": driver.get("code", ""),
                "constructor": constructor.get("name", ""),
                "grid": entry.get("grid"),
                "laps": entry.get("laps"),
                "status": entry.get("status"),
                "time": entry.get("Time", {}).get("time", ""),
                "points": entry.get("points"),
                "fastest_lap": entry.get("FastestLap", {}).get("Time", {}).get("time", ""),
            })
        return results


_provider: F1Provider | None = None

def get_f1_provider() -> F1Provider:
    global _provider
    if _provider is None:
        _provider = F1Provider()
    return _provider
