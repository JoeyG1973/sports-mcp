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


from sports_mcp.tools import _detect_offseason, _detect_postseason


def test_detect_offseason_future_start_date():
    payload = {"season": {"startDate": "2099-08-06T07:00Z"}}
    assert _detect_offseason(payload) is True


def test_detect_offseason_past_start_date():
    payload = {"season": {"startDate": "2020-08-06T07:00Z"}}
    assert _detect_offseason(payload) is False


def test_detect_offseason_no_season_block():
    assert _detect_offseason({}) is False


def test_detect_offseason_unparseable_date():
    payload = {"season": {"startDate": "garbage"}}
    assert _detect_offseason(payload) is False


def test_detect_postseason_one_eliminated_team():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "clincher", "displayValue": "x"}]},
                        {"stats": [{"name": "clincher", "displayValue": "e"}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is True


def test_detect_postseason_no_eliminations():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "clincher", "displayValue": "x"}]},
                        {"stats": [{"name": "clincher", "displayValue": "y"}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is False


def test_detect_postseason_no_clinch_stat():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "wins", "value": 25}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is False


def test_detect_postseason_empty_payload():
    assert _detect_postseason({}) is False


async def test_get_standings_offseason_nfl():
    payload = {
        "name": "NFL Standings",
        "season": {"startDate": "2099-08-06T07:00Z"},
        "children": [
            {
                "name": "AFC East",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Buffalo Bills"},
                            "stats": [
                                {"name": "wins", "value": 12},
                                {"name": "losses", "value": 5},
                                {"name": "clincher", "displayValue": "y"},
                            ],
                        },
                        {
                            "team": {"displayName": "Miami Dolphins"},
                            "stats": [
                                {"name": "wins", "value": 9},
                                {"name": "losses", "value": 8},
                                {"name": "clincher", "displayValue": "e"},
                            ],
                        },
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NFL")
    finally:
        await c.aclose()
    assert s.startswith("The NFL is in the offseason. Last season. ")
    assert "Buffalo Bills first at 12 wins and 5 losses, qualified for the playoffs." in s
    assert "Miami Dolphins second at 9 wins and 8 losses, did not qualify for the playoffs." in s


async def test_get_standings_postseason_nhl():
    payload = {
        "name": "NHL Standings",
        "season": {"startDate": "2020-09-20T07:00Z"},
        "children": [
            {
                "name": "Eastern Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Carolina Hurricanes"},
                            "stats": [
                                {"name": "wins", "value": 53},
                                {"name": "losses", "value": 20},
                                {"name": "clincher", "displayValue": "z"},
                            ],
                        },
                        {
                            "team": {"displayName": "New Jersey Devils"},
                            "stats": [
                                {"name": "wins", "value": 42},
                                {"name": "losses", "value": 37},
                                {"name": "clincher", "displayValue": "e"},
                            ],
                        },
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NHL")
    finally:
        await c.aclose()
    assert s.startswith("The NHL is in the playoffs. ")
    assert "Carolina Hurricanes first at 53 wins and 20 losses, qualified for the playoffs." in s
    assert "New Jersey Devils second at 42 wins and 37 losses, did not qualify for the playoffs." in s


async def test_get_standings_regular_season_unchanged():
    payload = {
        "name": "NBA Standings",
        "season": {"startDate": "2020-10-01T07:00Z"},
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
                        }
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    # No prefix, no per-team annotation. Output is exactly the pre-change format.
    assert s == "Eastern Conference. Boston Celtics first at 52 wins and 18 losses."


async def test_get_standings_postseason_no_clinch_data():
    """League past regular season but ESPN response lacks clincher stat per team.

    With no clinch data, _detect_postseason returns False. So the prefix
    is empty and no per-team annotations are added. This is the safe
    fallback path described in the spec.
    """
    payload = {
        "name": "Premier League",
        "season": {"startDate": "2020-08-01T07:00Z"},
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
    assert s == "Premier League. Arsenal first at 25 wins and 5 losses."


async def test_get_league_status_scheduled_no_short_detail():
    """ESPN's pre-state events often have shortDetail='Scheduled'. The
    output must read 'scheduled.' once, not 'scheduled Scheduled.'.
    """
    payload = {
        "leagues": [{"season": {"type": {"name": "Group Stage"}}}],
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "South Africa"}, "score": "0", "homeAway": "away"},
                            {"team": {"displayName": "Mexico"}, "score": "0", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "pre", "shortDetail": "Scheduled"}},
                    }
                ],
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "World Cup")
    finally:
        await c.aclose()
    assert "scheduled Scheduled" not in s
    assert "South Africa at Mexico, scheduled." in s


async def test_get_league_status_world_cup_pre_tournament_fallback():
    """When the scoreboard returns no events and the league season's
    startDate is in the future, the fallback message acknowledges the
    tournament cycle.
    """
    payload = {
        "leagues": [
            {
                "season": {
                    "type": {"name": "Off Season"},
                    "startDate": "2099-06-11T00:00Z",
                }
            }
        ],
        "events": [],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "World Cup")
    finally:
        await c.aclose()
    assert s == (
        "The World Cup is in the offseason. "
        "No current events. The tournament may not have started yet."
    )


import pytest

from sports_mcp.format import no_punctuation_artifacts


@pytest.mark.parametrize(
    "tool_name,arg",
    [
        ("get_live_score", "Quidditch United"),
        ("get_next_game", "Quidditch United"),
        ("get_standings", "Quidditch"),
        ("get_league_status", "Quidditch"),
    ],
)
async def test_no_tool_returns_empty_for_unknown_input(tool_name, arg):
    """No tool may return an empty string for an unrecognized league or team."""
    from sports_mcp import tools as t
    tool = getattr(t, tool_name)
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await tool(c, arg)
    finally:
        await c.aclose()
    assert s != ""
    assert no_punctuation_artifacts(s)


@pytest.mark.parametrize(
    "tool_name,arg",
    [
        ("get_live_score", "Lakers"),
        ("get_next_game", "Lakers"),
        ("get_standings", "NBA"),
        ("get_league_status", "NBA"),
    ],
)
async def test_no_tool_returns_empty_when_espn_unreachable(tool_name, arg):
    """No tool may return an empty string when ESPN raises a connection error."""
    from sports_mcp import tools as t
    tool = getattr(t, tool_name)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await tool(c, arg)
    finally:
        await c.aclose()
    assert s != ""
    assert no_punctuation_artifacts(s)


async def test_no_tool_returns_empty_with_minimal_payload():
    """get_standings and get_league_status with empty children/events
    must still produce a non-empty string.
    """
    from sports_mcp import tools as t

    standings_payload = {"name": "X", "children": []}
    c = make_client(lambda r: httpx.Response(200, json=standings_payload))
    try:
        s = await t.get_standings(c, "NBA")
    finally:
        await c.aclose()
    assert s != ""
    assert no_punctuation_artifacts(s)

    league_status_payload = {"leagues": [], "events": []}
    c = make_client(lambda r: httpx.Response(200, json=league_status_payload))
    try:
        s = await t.get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert s != ""
    assert no_punctuation_artifacts(s)
