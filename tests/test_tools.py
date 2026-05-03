"""Tests for the four MCP tool functions.

Each tool is tested with: a happy path, an empty-result path, and an
ESPN-unreachable path. ESPN responses are mocked; alias resolution is real.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sports_mcp.espn import ESPNClient
from sports_mcp.tools import get_live_score, get_next_game

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def make_client(handler) -> ESPNClient:
    return ESPNClient(transport=httpx.MockTransport(handler))


async def test_get_live_score_unknown_team():
    c = make_client(lambda r: httpx.Response(200, json={"events": []}))
    try:
        s = await get_live_score(c, "Quidditch United")
    finally:
        await c.aclose()
    assert "I don't recognize" in s
    assert "Quidditch United" in s


async def test_get_live_score_ambiguous_team():
    # Build a synthetic scoreboard that won't be reached.
    c = make_client(lambda r: httpx.Response(200, json={"events": []}))
    try:
        s = await get_live_score(c, "Giants")
    finally:
        await c.aclose()
    assert s.startswith("Giants is ambiguous.")


async def test_get_live_score_no_live_game(monkeypatch):
    # A scoreboard with the Lakers in a 'pre' state (scheduled, not started).
    payload = {
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "0", "homeAway": "home"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "0", "homeAway": "away"},
                        ],
                        "status": {"type": {"state": "pre", "description": "Scheduled"}, "period": 0, "displayClock": "0:00"},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert "Lakers" in s
    assert "do not have a live game" in s or "don't have a live game" in s


async def test_get_live_score_live_game():
    payload = {
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "89", "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "91", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "in", "description": "In Progress"}, "period": 4, "displayClock": "2:34"},
                    }
                ],
            }
        ],
        "leagues": [{"slug": "nba"}],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert "Los Angeles Lakers 89" in s
    assert "Boston Celtics 91" in s
    assert "fourth quarter" in s
    assert "2 minutes 34 seconds" in s


async def test_get_live_score_espn_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s


async def test_get_next_game_unknown_team():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_next_game(c, "Quidditch United")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_next_game_no_upcoming():
    payload = {"events": []}
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "do not have a scheduled game" in s


async def test_get_next_game_with_upcoming():
    # ESPN returns ISO 8601 UTC. Pick a date several months out so the
    # weekday/calendar phrasing doesn't depend on test-run date.
    payload = {
        "events": [
            {
                "id": "1",
                "date": "2099-12-25T01:00Z",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "homeAway": "home"},
                        ],
                        "venue": {"fullName": "TD Garden"},
                        "status": {"type": {"state": "pre"}},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "Los Angeles Lakers" in s
    assert "Boston Celtics" in s
    assert "TD Garden" in s


async def test_get_next_game_espn_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s


from sports_mcp.tools import get_standings, get_league_status


async def test_get_standings_unknown_league():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_standings(c, "Quidditch")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_standings_two_conferences():
    payload = {
        "name": "NBA Standings",
        "children": [
            {
                "name": "Eastern Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Boston Celtics"},
                            "stats": [
                                {"name": "wins", "value": 52},
                                {"name": "losses", "value": 18},
                            ],
                        },
                        {
                            "team": {"displayName": "Milwaukee Bucks"},
                            "stats": [
                                {"name": "wins", "value": 48},
                                {"name": "losses", "value": 22},
                            ],
                        },
                    ]
                },
            },
            {
                "name": "Western Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Denver Nuggets"},
                            "stats": [
                                {"name": "wins", "value": 50},
                                {"name": "losses", "value": 20},
                            ],
                        }
                    ]
                },
            },
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    assert "Eastern Conference" in s
    assert "Western Conference" in s
    assert "Boston Celtics first at 52 wins and 18 losses" in s


async def test_get_standings_single_table():
    payload = {
        "name": "Premier League",
        "children": [
            {
                "name": "Premier League",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Arsenal"},
                            "stats": [
                                {"name": "wins", "value": 25},
                                {"name": "losses", "value": 5},
                            ],
                        }
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "Premier League")
    finally:
        await c.aclose()
    assert "Arsenal first at 25 wins and 5 losses" in s


async def test_get_standings_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s


async def test_get_league_status_in_season_with_games():
    payload = {
        "leagues": [
            {
                "season": {"type": {"name": "Regular Season"}},
                "calendar": [],
            }
        ],
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Lakers"}, "score": "0", "homeAway": "away"},
                            {"team": {"displayName": "Celtics"}, "score": "0", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "pre", "shortDetail": "7:30 PM ET"}},
                    }
                ],
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "The NBA is in the regular season" in s
    assert "Lakers" in s and "Celtics" in s


async def test_get_league_status_no_games():
    payload = {
        "leagues": [{"season": {"type": {"name": "Off Season"}}}],
        "events": [],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "No games today" in s


async def test_get_league_status_unknown_league():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_league_status(c, "Quidditch")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_league_status_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s


async def test_get_league_status_scheduled_event_has_no_colon_or_et():
    payload = {
        "leagues": [{"season": {"type": {"name": "Regular Season"}}}],
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Lakers"}, "score": "0", "homeAway": "away"},
                            {"team": {"displayName": "Celtics"}, "score": "0", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "pre", "shortDetail": "7:30 PM ET"}},
                    }
                ],
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert ":" not in s
    assert " ET" not in s and " ET." not in s
    assert "eastern" in s


async def test_get_live_score_post_state_win():
    payload = {
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "91", "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "89", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "post", "description": "Final"}, "period": 4, "displayClock": "0:00"},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert s == "The Los Angeles Lakers beat the Boston Celtics 91 to 89."


async def test_get_live_score_post_state_loss():
    payload = {
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "89", "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "91", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "post", "description": "Final"}, "period": 4, "displayClock": "0:00"},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert s == "The Los Angeles Lakers lost to the Boston Celtics 89 to 91."


async def test_get_live_score_pre_state_today(monkeypatch):
    import datetime as _test_dt
    fixed_now = _test_dt.datetime(2099, 12, 25, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    payload = {
        "events": [
            {
                "id": "1",
                "date": "2099-12-26T01:30Z",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "0", "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "0", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "pre", "description": "Scheduled"}, "period": 0, "displayClock": "0:00"},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    # Lakers are away (id 13 vs home id 2), so verb is "play".
    # The exact time string depends on host timezone; assert structural pieces.
    assert "Los Angeles Lakers don't have a live game yet" in s
    assert "play the Boston Celtics" in s
    assert "PM" in s or "AM" in s
    assert "(" not in s and ")" not in s
