"""Tiny in-memory TTL cache for HTTP responses."""
import time
from typing import Any, Callable


class TTLCache:
    """Process-local cache with per-entry TTL and lazy expiry on read."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._clock = clock

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._store[key] = (value, self._clock() + ttl_seconds)
