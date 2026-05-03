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
