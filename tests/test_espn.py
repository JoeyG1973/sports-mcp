import json
from pathlib import Path

import httpx
import pytest

from sports_mcp.espn import ESPNClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def captured_urls():
    return []


@pytest.fixture
def mock_transport(captured_urls):
    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        if "/scoreboard" in request.url.path and "basketball/nba" in request.url.path:
            return httpx.Response(200, json=load("nba_scoreboard.json"))
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
async def client(mock_transport):
    c = ESPNClient(transport=mock_transport)
    yield c
    await c.aclose()


async def test_scoreboard_uses_site_v2_path(client, captured_urls):
    await client.scoreboard("basketball/nba")
    assert any(
        "site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard" in u
        for u in captured_urls
    )


async def test_standings_uses_v2_path_without_site():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, json={"name": "stub", "children": []})

    transport = httpx.MockTransport(handler)
    c = ESPNClient(transport=transport)
    try:
        await c.standings("basketball/nba")
    finally:
        await c.aclose()
    assert len(captured) == 1
    assert "site.api.espn.com/apis/v2/sports/basketball/nba/standings" in captured[0]
    assert "/apis/site/v2/" not in captured[0]


async def test_cache_hit_skips_second_request(captured_urls, mock_transport):
    c = ESPNClient(transport=mock_transport)
    try:
        await c.scoreboard("basketball/nba")
        await c.scoreboard("basketball/nba")
    finally:
        await c.aclose()
    assert len(captured_urls) == 1


async def test_team_schedule_fetches_and_returns():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/teams/13/schedule" in request.url.path:
            return httpx.Response(200, json=load("nba_team_schedule.json"))
        return httpx.Response(404, json={})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        data = await c.team_schedule("basketball/nba", "13")
    finally:
        await c.aclose()
    assert "events" in data or "team" in data


async def test_standings_returns_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("nba_standings.json"))

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        data = await c.standings("basketball/nba")
    finally:
        await c.aclose()
    assert "children" in data or "name" in data


async def test_http_5xx_raises_status_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await c.scoreboard("basketball/nba")
    finally:
        await c.aclose()


async def test_dates_param_appended():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, json={"events": [], "leagues": []})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        await c.scoreboard("basketball/nba", dates="20260508")
    finally:
        await c.aclose()
    assert "dates=20260508" in captured[0]
