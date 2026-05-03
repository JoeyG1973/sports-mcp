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
