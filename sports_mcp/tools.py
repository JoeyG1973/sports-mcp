"""The four MCP tool functions.

Each tool returns a TTS-safe string and never raises. HTTP and slug-map
errors are translated into prose and logged.
"""
from __future__ import annotations

import datetime as _dt
import difflib
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

    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if home is None or away is None:
        return f"The {info.name} do not have a live game right now."

    is_home = str((home.get("team") or {}).get("id")) == info.espn_id
    team_competitor = home if is_home else away
    opp_competitor = away if is_home else home

    if state == "post":
        return fmt.final_outcome_line(
            team_name=info.name,
            team_score=int(team_competitor.get("score", 0)),
            opp_name=opp_competitor["team"]["displayName"],
            opp_score=int(opp_competitor.get("score", 0)),
        )

    if state == "pre":
        when = _parse_event_datetime(event.get("date") or "")
        if when is None:
            return f"The {info.name} do not have a live game right now."
        return fmt.pre_game_line(
            team_name=info.name,
            opp_name=opp_competitor["team"]["displayName"],
            when=when,
            is_home=is_home,
        )

    if state != "in":
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


def _stat_value(entry: dict, name: str) -> int:
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return int(stat.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _detect_offseason(standings_data: dict) -> bool:
    """Return True if the standings response describes an upcoming season.

    ESPN's standings endpoint returns the most recently completed season's
    records during a league's offseason; the 'season' block then carries
    the startDate of the *next* season. If that startDate is in the future,
    we are in offseason.
    """
    season = standings_data.get("season") or {}
    start_iso = season.get("startDate") or ""
    if not start_iso:
        return False
    parsed = _parse_event_datetime(start_iso)
    if parsed is None:
        return False
    now = _dt.datetime.now(_dt.timezone.utc)
    return parsed > now


def _detect_postseason(standings_data: dict) -> bool:
    """Return True if any team in the standings has been eliminated.

    ESPN exposes per-team playoff status as a 'clincher' stat. The value
    'e' means eliminated. A non-empty set of eliminations confirms the
    regular season is over and postseason is underway. If no entry carries
    a clincher stat, return False (the league either is mid-regular-season
    or does not instrument playoffs).
    """
    for child in standings_data.get("children") or []:
        entries = ((child.get("standings") or {}).get("entries")) or []
        for entry in entries:
            for stat in entry.get("stats") or []:
                if stat.get("name") == "clincher" and stat.get("displayValue") == "e":
                    return True
    return False


def _qualification_from_clinch(entry: dict) -> str | None:
    """Translate ESPN's 'clincher' stat into 'qualified', 'eliminated', or None."""
    for stat in entry.get("stats") or []:
        if stat.get("name") == "clincher":
            value = stat.get("displayValue") or ""
            if value in ("x", "y", "z"):
                return "qualified"
            if value == "e":
                return "eliminated"
            return None
    return None


def _rows_from_standings_entries(
    entries: list[dict],
    annotate_qualification: bool = False,
) -> list[dict]:
    """Convert ESPN standings entries into the dict shape standings_block expects.

    When annotate_qualification is True, each row gets an optional
    'qualification' key derived from the 'clincher' stat. When False, no
    qualification key is emitted (preserves the regular-season output).
    """
    rows: list[dict] = []
    for e in entries:
        team_name = (e.get("team") or {}).get("displayName") or ""
        row: dict = {
            "name": team_name,
            "wins": _stat_value(e, "wins"),
            "losses": _stat_value(e, "losses"),
        }
        if annotate_qualification:
            qualification = _qualification_from_clinch(e)
            if qualification is not None:
                row["qualification"] = qualification
        rows.append(row)
    return rows


def _league_alias_strings() -> list[str]:
    out: list[str] = []
    for li in LEAGUE_REGISTRY:
        out.extend(li.aliases)
        out.append(li.name.lower())
    return out


async def get_standings(client: ESPNClient, league: str) -> str:
    info = resolve_league(league)
    if info is None:
        suggestions = difflib.get_close_matches(
            league.lower(), _league_alias_strings(), n=3, cutoff=0.6
        )
        return fmt.unknown_league_message(league, list(suggestions))

    try:
        data = await client.standings(info.slug)
    except httpx.HTTPError as e:
        log.warning("standings fetch failed: %s", e)
        return ESPN_UNREACHABLE

    children = data.get("children") or []
    if not children:
        return f"{info.name} standings are not available."

    if _detect_offseason(data):
        phase = "offseason"
    elif _detect_postseason(data):
        phase = "postseason"
    else:
        phase = "regular"

    annotate = phase != "regular"
    blocks: list[str] = []
    for child in children:
        label = child.get("name") or info.name
        entries = ((child.get("standings") or {}).get("entries")) or []
        rows = _rows_from_standings_entries(entries, annotate_qualification=annotate)
        blocks.append(fmt.standings_block(label, rows))
    return fmt.season_phase_prefix(info.name, phase) + " ".join(blocks)


def _season_phrase(league_block: dict) -> str:
    season = (league_block.get("season") or {})
    type_block = season.get("type") or {}
    type_name = (type_block.get("name") or "").lower().strip()
    if not type_name or "off" in type_name:
        return "offseason"
    # Common ESPN values: 'preseason', 'regular season', 'postseason'
    return type_name


def _sanitize_short_detail(short: str) -> str:
    """Strip TTS-unfriendly punctuation and timezone abbreviations from ESPN's shortDetail."""
    if not short:
        return ""
    cleaned = short.replace("/", " ").replace("(", "").replace(")", "").replace(":", " ")
    # Timezone abbreviations: replace whole-word matches.
    tz_map = {
        " ET": " eastern",
        " PT": " pacific",
        " CT": " central",
        " MT": " mountain",
        " AKT": " alaska",
        " HST": " hawaii",
        " HT": " hawaii",
    }
    for abbr, full in tz_map.items():
        if cleaned.endswith(abbr):
            cleaned = cleaned[: -len(abbr)] + full
        else:
            cleaned = cleaned.replace(abbr + " ", full + " ")
    return cleaned.strip()


def _events_phrase_for_status(events: list[dict]) -> str:
    if not events:
        return ""
    sentences: list[str] = []
    for event in events:
        comp = _competition_of_event(event)
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home is None or away is None:
            continue
        status = comp.get("status", {})
        state = (status.get("type") or {}).get("state")
        short = _sanitize_short_detail((status.get("type") or {}).get("shortDetail") or "")
        if state == "in":
            tail = "in progress"
        elif state == "post":
            tail = "final"
        else:
            short_clean = short.strip()
            if not short_clean or short_clean.lower() == "scheduled":
                tail = "scheduled"
            else:
                tail = f"scheduled {short_clean}"
        sentences.append(
            f"{away['team']['displayName']} at {home['team']['displayName']}, {tail}."
        )
    return " ".join(sentences)


async def get_league_status(client: ESPNClient, league: str) -> str:
    info = resolve_league(league)
    if info is None:
        suggestions = difflib.get_close_matches(
            league.lower(), _league_alias_strings(), n=3, cutoff=0.6
        )
        return fmt.unknown_league_message(league, list(suggestions))

    try:
        data = await client.scoreboard(info.slug)
    except httpx.HTTPError as e:
        log.warning("scoreboard fetch failed: %s", e)
        return ESPN_UNREACHABLE

    leagues = data.get("leagues") or []
    league_block = leagues[0] if leagues else {}
    season_phrase = _season_phrase(league_block)
    events_phrase = _events_phrase_for_status(data.get("events") or [])
    is_pre_tournament = _detect_offseason(league_block)
    return fmt.league_status_block(
        info.name,
        season_phrase,
        events_phrase,
        is_pre_tournament=is_pre_tournament,
    )
