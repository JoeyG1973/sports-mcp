"""The four MCP tool functions.

Each tool returns a TTS-safe string and never raises. HTTP and slug-map
errors are translated into prose and logged.
"""
from __future__ import annotations

import datetime as _dt
import logging

import httpx

from sports_mcp import format as fmt
from sports_mcp.aliases import (
    LEAGUE_REGISTRY,
    LeagueInfo,
    TeamInfo,
    TeamMatchAmbiguous,
    TeamMatchNone,
    TeamMatchOne,
    resolve_league,
    resolve_team,
)
from sports_mcp.espn import ESPNClient

log = logging.getLogger(__name__)

ESPN_UNREACHABLE = "Couldn't reach ESPN, try again in a moment."


def _league_for_slug(slug: str) -> LeagueInfo | None:
    for li in LEAGUE_REGISTRY:
        if li.slug == slug:
            return li
    return None


def _ambiguity_candidates(teams: tuple[TeamInfo, ...]) -> list[str]:
    out: list[str] = []
    for t in teams:
        li = _league_for_slug(t.league_slug)
        league_name = li.name if li else t.league_slug
        out.append(f"the {league_name} {t.name.split()[-1]}")
    return out


def _period_phrase(sport: str, period: int, status_type: dict) -> str:
    if sport == "basketball":
        return fmt.period_phrase_basketball(period)
    if sport == "football":
        return fmt.period_phrase_football(period)
    if sport == "hockey":
        return fmt.period_phrase_hockey(period)
    if sport == "baseball":
        # Baseball uses 'period' for inning; half is in description text.
        desc = (status_type or {}).get("detail", "") + " " + (status_type or {}).get("description", "")
        half = "top" if "Top" in desc or "top" in desc else "bottom"
        return fmt.period_phrase_baseball(period, half)
    if sport == "soccer":
        return fmt.period_phrase_soccer(period)
    return f"period {period}"


def _find_event_for_team(events: list[dict], team_id: str) -> dict | None:
    for event in events:
        for comp in event.get("competitions", []):
            for c in comp.get("competitors", []):
                team = c.get("team", {})
                if str(team.get("id")) == team_id:
                    return event
    return None


def _competition_of_event(event: dict) -> dict:
    comps = event.get("competitions", [])
    return comps[0] if comps else {}


async def get_live_score(client: ESPNClient, team: str) -> str:
    match = resolve_team(team)
    if isinstance(match, TeamMatchNone):
        return fmt.unknown_team_message(team, match.suggestions)
    if isinstance(match, TeamMatchAmbiguous):
        return fmt.ambiguity_message(team, _ambiguity_candidates(match.teams))
    assert isinstance(match, TeamMatchOne)
    info = match.team

    league = _league_for_slug(info.league_slug)
    if league is None:
        log.error("Team %s has unknown league slug %s", info.name, info.league_slug)
        return ESPN_UNREACHABLE

    try:
        data = await client.scoreboard(info.league_slug)
    except httpx.HTTPError as e:
        log.warning("scoreboard fetch failed: %s", e)
        return ESPN_UNREACHABLE

    event = _find_event_for_team(data.get("events", []), info.espn_id)
    if event is None:
        return f"The {info.name} do not have a live game right now."

    comp = _competition_of_event(event)
    status = comp.get("status", {})
    state = (status.get("type") or {}).get("state")
    period = int(status.get("period") or 0)
    clock = status.get("displayClock") or ""

    if state != "in":
        return f"The {info.name} do not have a live game right now."

    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if home is None or away is None:
        return f"The {info.name} do not have a live game right now."

    period_text = _period_phrase(league.sport, period, status.get("type") or {})
    clock_text = fmt.clock_phrase(clock)

    return fmt.score_line(
        away_name=away["team"]["displayName"],
        away_score=int(away.get("score", 0)),
        home_name=home["team"]["displayName"],
        home_score=int(home.get("score", 0)),
        period_text=period_text,
        clock_text=clock_text,
    )


def _parse_event_datetime(iso: str) -> _dt.datetime | None:
    # ESPN uses '2026-05-08T19:30Z'; Python wants '+00:00' or use fromisoformat with Z.
    if not iso:
        return None
    try:
        return _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _next_event_for_team(events: list[dict], team_id: str) -> dict | None:
    """Return the soonest future event involving team_id, or None."""
    now = _dt.datetime.now(_dt.timezone.utc)
    candidates: list[tuple[_dt.datetime, dict]] = []
    for event in events:
        when = _parse_event_datetime(event.get("date") or "")
        if when is None or when < now:
            continue
        for comp in event.get("competitions", []):
            for c in comp.get("competitors", []):
                if str((c.get("team") or {}).get("id")) == team_id:
                    candidates.append((when, event))
                    break
    candidates.sort(key=lambda kv: kv[0])
    return candidates[0][1] if candidates else None


async def get_next_game(client: ESPNClient, team: str) -> str:
    match = resolve_team(team)
    if isinstance(match, TeamMatchNone):
        return fmt.unknown_team_message(team, match.suggestions)
    if isinstance(match, TeamMatchAmbiguous):
        return fmt.ambiguity_message(team, _ambiguity_candidates(match.teams))
    assert isinstance(match, TeamMatchOne)
    info = match.team

    try:
        data = await client.team_schedule(info.league_slug, info.espn_id)
    except httpx.HTTPError as e:
        log.warning("team_schedule fetch failed: %s", e)
        return ESPN_UNREACHABLE

    events = data.get("events") or []
    event = _next_event_for_team(events, info.espn_id)
    if event is None:
        return f"The {info.name} do not have a scheduled game on the calendar."

    when = _parse_event_datetime(event.get("date") or "")
    comp = _competition_of_event(event)
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    venue = (comp.get("venue") or {}).get("fullName") or ""

    if home is None or away is None or when is None:
        return f"The {info.name} do not have a scheduled game on the calendar."

    home_name = home["team"]["displayName"]
    away_name = away["team"]["displayName"]
    is_home = home["team"]["id"] == info.espn_id

    date_str = fmt.date_phrase(when)
    time_str = fmt.time_phrase(when)
    opponent = home_name if not is_home else away_name
    location_phrase = f"at {venue}" if venue else ""

    if is_home:
        sentence = f"The {info.name} host the {opponent} {date_str} at {time_str}"
    else:
        sentence = f"The {info.name} play the {opponent} {date_str} at {time_str}"
    if location_phrase:
        sentence = f"{sentence} {location_phrase}"
    return sentence + "."
