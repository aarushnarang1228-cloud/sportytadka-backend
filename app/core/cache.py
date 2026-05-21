"""
Simple in-memory TTL cache.

Why not Redis? For MVP traffic (hundreds of users, not thousands), an in-memory
dict with TTL expiration is perfectly fine. It runs inside the same process,
has zero latency, zero cost, and zero infrastructure. When traffic grows past
what a single Render instance handles, swap this for Redis — the interface
(get/set/delete) stays the same.

Limitation: cache is per-process. If you scale to multiple workers, each has
its own cache. That's acceptable for MVP — stale data for a few seconds
across workers is fine for sports scores.
"""

import time
from typing import Any


class TTLCache:
    """Thread-safe-ish TTL cache using a plain dict."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if it exists and hasn't expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        """Store a value with a TTL in seconds."""
        self._store[key] = (value, time.time() + ttl_seconds)

    def delete(self, key: str) -> None:
        """Remove a key from cache."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Flush everything."""
        self._store.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)


# Global cache instance — import this wherever you need caching
cache = TTLCache()
