"""Async ESPN HTTP client with TTL caching and two-base-URL routing.

ESPN exposes scoreboard/teams/schedule under /apis/site/v2/ and standings
under /apis/v2/ (the 'site' segment is dropped). Hitting the wrong base
returns either 404s or stub responses. This client routes correctly per
endpoint type.
"""

from __future__ import annotations

from typing import Any

import httpx

from sports_mcp.cache import TTLCache

_BASE_SITE_V2 = "https://site.api.espn.com/apis/site/v2"
_BASE_V2 = "https://site.api.espn.com/apis/v2"

DEFAULT_TIMEOUT = 8.0


class ESPNClient:
    """Async wrapper around ESPN's hidden HTTP API."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        cache: TTLCache | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._cache = cache or TTLCache()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, ttl_seconds: float) -> dict[str, Any]:
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        response = await self._client.get(url)
        response.raise_for_status()
        data = response.json()
        self._cache.set(url, data, ttl_seconds)
        return data

    async def scoreboard(self, league_slug: str, dates: str | None = None) -> dict[str, Any]:
        url = f"{_BASE_SITE_V2}/sports/{league_slug}/scoreboard"
        if dates:
            url = f"{url}?dates={dates}"
        return await self._get_json(url, ttl_seconds=15.0)

    async def team_schedule(self, league_slug: str, team_id: str) -> dict[str, Any]:
        url = f"{_BASE_SITE_V2}/sports/{league_slug}/teams/{team_id}/schedule"
        return await self._get_json(url, ttl_seconds=300.0)

    async def standings(self, league_slug: str) -> dict[str, Any]:
        url = f"{_BASE_V2}/sports/{league_slug}/standings"
        return await self._get_json(url, ttl_seconds=300.0)
