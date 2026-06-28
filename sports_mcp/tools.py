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

# National-team / tournament leagues whose per-team schedule feed omits
# not-yet-played knockout fixtures (it carries only group games). Their
# upcoming games are read from the competition scoreboard instead.
_TOURNAMENT_NEXT_GAME_SLUGS = frozenset({"soccer/fifa.world"})

# How far ahead to scan the tournament scoreboard for the next fixture.
# Comfortably spans a World Cup knockout bracket (Round of 32 to final).
_NEXT_GAME_WINDOW_DAYS = 60

# Substrings marking a not-yet-decided knockout opponent (e.g. "Group J 2nd
# Place", "Round of 32 1 Winner"). Such placeholders are not real team names.
_PLACEHOLDER_OPPONENT_MARKERS = ("winner", "place", "runner", "tbd", "to be")

# Substrings marking a championship/series name rather than a team. Queries like
# "who won the NBA Finals?" name an event, not a team, so there is nothing to
# resolve — redirect instead of emitting fuzzy team guesses or a wrong game.
_EVENT_NAME_MARKERS = (
    "finals",
    "final",
    "playoff",
    "championship",
    "world series",
    "super bowl",
    "stanley cup",
)


def _looks_like_event_name(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _EVENT_NAME_MARKERS)


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
        desc = (
            (status_type or {}).get("detail", "") + " " + (status_type or {}).get("description", "")
        )
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
        if _looks_like_event_name(team):
            return fmt.ask_for_team_message()
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
    now = _dt.datetime.now(_dt.UTC)
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


def _is_placeholder_opponent(name: str) -> bool:
    """True if the opponent is an unresolved knockout slot, not a real team.

    ESPN fills not-yet-decided brackets with names like "Group J 2nd Place" or
    "Round of 32 1 Winner" — and these often carry TTS-unsafe punctuation
    (e.g. "Third Place Group E/F/G/I/J"). Naming them aloud is useless and
    unsafe, so we phrase the fixture without the opponent.
    """
    if not name:
        return True
    low = name.lower()
    if any(marker in low for marker in _PLACEHOLDER_OPPONENT_MARKERS):
        return True
    return not fmt.no_punctuation_artifacts(name)


def _format_next_event(info: TeamInfo, event: dict) -> str | None:
    """Render a TTS-safe next-game line, or None if the event is unusable."""
    when = _parse_event_datetime(event.get("date") or "")
    comp = _competition_of_event(event)
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if home is None or away is None or when is None:
        return None

    is_home = str((home.get("team") or {}).get("id")) == info.espn_id
    opp = away if is_home else home
    opp_name = (opp.get("team") or {}).get("displayName") or ""
    venue = (comp.get("venue") or {}).get("fullName") or ""

    date_str = fmt.date_phrase(when)
    time_str = fmt.time_phrase(when)
    verb = "host" if is_home else "play"
    location_phrase = f" at {venue}" if venue and fmt.no_punctuation_artifacts(venue) else ""

    if _is_placeholder_opponent(opp_name):
        sentence = f"The {info.name} {verb} their next match {date_str} at {time_str}"
    else:
        sentence = f"The {info.name} {verb} the {opp_name} {date_str} at {time_str}"
    return f"{sentence}{location_phrase}."


async def _next_game_from_scoreboard(client: ESPNClient, info: TeamInfo) -> str:
    """Next fixture for a tournament team, read from the competition scoreboard.

    The per-team schedule feed omits unplayed knockout games, so scan a forward
    window of the scoreboard for the soonest future event involving the team.
    """
    now = _dt.datetime.now(_dt.UTC)
    end = now + _dt.timedelta(days=_NEXT_GAME_WINDOW_DAYS)
    dates = f"{now:%Y%m%d}-{end:%Y%m%d}"
    try:
        data = await client.scoreboard(info.league_slug, dates=dates)
    except httpx.HTTPError as e:
        log.warning("scoreboard fetch failed: %s", e)
        return ESPN_UNREACHABLE

    event = _next_event_for_team(data.get("events") or [], info.espn_id)
    sentence = _format_next_event(info, event) if event is not None else None
    if sentence is None:
        return f"The {info.name} do not have a scheduled game on the calendar."
    return sentence


async def get_next_game(client: ESPNClient, team: str) -> str:
    match = resolve_team(team)
    if isinstance(match, TeamMatchNone):
        if _looks_like_event_name(team):
            return fmt.ask_for_team_message()
        return fmt.unknown_team_message(team, match.suggestions)
    if isinstance(match, TeamMatchAmbiguous):
        return fmt.ambiguity_message(team, _ambiguity_candidates(match.teams))
    assert isinstance(match, TeamMatchOne)
    info = match.team

    if info.league_slug in _TOURNAMENT_NEXT_GAME_SLUGS:
        return await _next_game_from_scoreboard(client, info)

    try:
        data = await client.team_schedule(info.league_slug, info.espn_id)
    except httpx.HTTPError as e:
        log.warning("team_schedule fetch failed: %s", e)
        return ESPN_UNREACHABLE

    event = _next_event_for_team(data.get("events") or [], info.espn_id)
    sentence = _format_next_event(info, event) if event is not None else None
    if sentence is None:
        return f"The {info.name} do not have a scheduled game on the calendar."
    return sentence


def _competitor_score(competitor: dict) -> int:
    """Read a competitor's score across ESPN's two score shapes.

    The scoreboard endpoint returns score as a string ("89"); the
    team_schedule endpoint returns a dict ({"value": 89.0, ...}). Both
    collapse to an int here, defaulting to 0 on missing or unparseable data.
    """
    score = competitor.get("score")
    if isinstance(score, dict):
        score = score.get("value", score.get("displayValue"))
    try:
        return int(float(score))
    except (TypeError, ValueError):
        return 0


def _completed_events_for_team(events: list[dict], team_id: str) -> list[dict]:
    """Return completed (post-state) events involving team_id, newest first."""
    candidates: list[tuple[_dt.datetime, dict]] = []
    for event in events:
        comp = _competition_of_event(event)
        state = ((comp.get("status") or {}).get("type") or {}).get("state")
        if state != "post":
            continue
        if not any(
            str((c.get("team") or {}).get("id")) == team_id for c in comp.get("competitors", [])
        ):
            continue
        when = _parse_event_datetime(event.get("date") or "")
        # Events with no parseable date sort last but are still reportable.
        candidates.append((when or _dt.datetime.min.replace(tzinfo=_dt.UTC), event))
    candidates.sort(key=lambda kv: kv[0], reverse=True)
    return [event for _, event in candidates]


# ESPN labels every sport's playoff rounds with the same generic bracket
# vocabulary (type id 14-17 = round of 16 / quarterfinal / semifinal / final),
# which is wrong for non-soccer leagues. Translate by (league, type id) to each
# league's own postseason round names. Keyed by ESPN competition.type.id.
#
# Verified live (2026 postseason): NBA and NHL both use ids 14-17 for their four
# playoff rounds. MLB and NFL also have four rounds and are mapped on the same
# id scheme; those mappings are pending live verification when their postseasons
# begin. An unmapped id falls back to the bare league name (never a soccer-style
# label), so the worst case is a missing round, not a wrong one.
_POSTSEASON_ROUNDS: dict[str, dict[str, str]] = {
    "NBA": {
        "14": "NBA first round",
        "15": "NBA conference semifinals",
        "16": "NBA conference finals",
        "17": "NBA Finals",
    },
    "NHL": {
        "14": "NHL first round",
        "15": "NHL second round",
        "16": "NHL conference finals",
        "17": "Stanley Cup Final",
    },
    "MLB": {
        "14": "Wild Card Series",
        "15": "Division Series",
        "16": "League Championship Series",
        "17": "World Series",
    },
    "NFL": {
        "14": "Wild Card round",
        "15": "Divisional round",
        "16": "Conference Championship",
        "17": "Super Bowl",
    },
}


def _competition_phrase(event: dict, league: LeagueInfo | None) -> str:
    """Compose a TTS-safe competition phrase, e.g. 'World Cup group stage'.

    Soccer keeps ESPN's round text (it is correct for cups: group stage, round
    of 16, quarterfinal, final). Non-soccer leagues translate ESPN's generic
    bracket round to their own postseason name via _POSTSEASON_ROUNDS. Regular
    season or unrecognized rounds yield just the league name.
    """
    comp = _competition_of_event(event)
    type_block = comp.get("type") or {}
    league_name = league.name if league else ""
    sport = league.sport if league else ""

    if sport == "soccer":
        round_text = (type_block.get("text") or "").strip()
        if league_name and round_text:
            return f"{league_name} {round_text.lower()}"
        return league_name or round_text

    type_id = str(type_block.get("id") or "")
    round_phrase = _POSTSEASON_ROUNDS.get(league_name, {}).get(type_id)
    return round_phrase or league_name


async def get_recent_results(client: ESPNClient, team: str, count: int = 1) -> str:
    match = resolve_team(team)
    if isinstance(match, TeamMatchNone):
        if _looks_like_event_name(team):
            return fmt.ask_for_team_message()
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

    completed = _completed_events_for_team(data.get("events") or [], info.espn_id)
    if not completed:
        return f"The {info.name} have no recent completed games."

    count = max(1, min(count, 5))
    league = _league_for_slug(info.league_slug)
    lines: list[str] = []
    for event in completed[:count]:
        comp = _competition_of_event(event)
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home is None or away is None:
            continue
        is_home = str((home.get("team") or {}).get("id")) == info.espn_id
        team_competitor = home if is_home else away
        opp_competitor = away if is_home else home
        lines.append(
            fmt.recent_result_line(
                team_name=info.name,
                team_score=_competitor_score(team_competitor),
                opp_name=opp_competitor["team"]["displayName"],
                opp_score=_competitor_score(opp_competitor),
                when=_parse_event_datetime(event.get("date") or ""),
                competition=_competition_phrase(event, league),
            )
        )
    if not lines:
        return f"The {info.name} have no recent completed games."
    return " ".join(lines)


# Approximate calendar window (start_month, start_day, end_month, end_day) when
# each league's championship is decided. Used to locate the most recently
# completed edition: a season-wide scoreboard query caps at the earliest ~100
# games (missing a recent final) and the postseason feed only tracks the current
# season, so neither reliably surfaces a title decided months ago. World Cup is
# quadrennial and intentionally omitted (handled by the recent-window fallback).
_CHAMPIONSHIP_WINDOWS = {
    "NFL": (1, 25, 2, 20),  # Super Bowl, early February
    "MLB": (10, 15, 11, 12),  # World Series, late October
    "NBA": (5, 20, 6, 30),  # Finals, June
    "NHL": (5, 20, 6, 30),  # Stanley Cup Final, June
    "MLS": (11, 20, 12, 20),  # MLS Cup, early December
    "Champions League": (5, 15, 6, 12),  # final, late May
}

# Look-back for leagues without a fixed window (e.g. World Cup).
_CHAMPION_FALLBACK_DAYS = 60

# ESPN competition.type id for an all-star game (e.g. the NFL Pro Bowl), which
# shares the post-season slug but is not a championship.
_ALL_STAR_TYPE_ID = "4"

# event.season.slug values that mark a soccer competition's title decider.
# Cups use 'final'; MLS tags its championship 'mls-cup' (its conference finals
# end in '---final' and must not be matched).
_SOCCER_FINAL_SLUGS = frozenset({"final", "mls-cup"})

# Spoken name of each league's championship (article included where natural).
_CHAMPIONSHIP_NAMES = {
    "NBA": "the NBA championship",
    "NHL": "the Stanley Cup",
    "MLB": "the World Series",
    "NFL": "the Super Bowl",
    "MLS": "MLS Cup",
    "World Cup": "the World Cup",
    "Champions League": "the Champions League",
    "Premier League": "the Premier League",
}

# Event/championship names mapped to a league. Plain league names fall through
# to resolve_league, so both "NBA championship" and "NBA" work.
_CHAMPIONSHIP_ALIASES = {
    "nba championship": "NBA",
    "nba finals": "NBA",
    "nba title": "NBA",
    "stanley cup": "NHL",
    "stanley cup final": "NHL",
    "stanley cup finals": "NHL",
    "nhl championship": "NHL",
    "world series": "MLB",
    "mlb championship": "MLB",
    "super bowl": "NFL",
    "nfl championship": "NFL",
    "mls cup": "MLS",
    "mls championship": "MLS",
    "fifa world cup": "World Cup",
    "champions league final": "Champions League",
    "champions league title": "Champions League",
}

CHAMPION_HELP = (
    "I can tell you the champion of the NBA, NHL, MLB, NFL, MLS, "
    "World Cup, or Champions League. Which one?"
)


def _resolve_competition(text: str) -> LeagueInfo | None:
    """Resolve a championship or league name to a LeagueInfo, or None."""
    key = text.strip().lower()
    if key.startswith("the "):
        key = key[4:]
    mapped = _CHAMPIONSHIP_ALIASES.get(key)
    if mapped is not None:
        return resolve_league(mapped)
    return resolve_league(text)


def _event_type_id(event: dict) -> str:
    return str((_competition_of_event(event).get("type") or {}).get("id") or "")


def _championship_event(events: list[dict], sport: str) -> dict | None:
    """Pick the championship-deciding game from a set of events, or None.

    Soccer finals carry event.season.slug == 'final'. Non-soccer: prefer the
    final round (competition.type.id '17', used by NBA, NHL, MLB); if no round
    is tagged (NFL keeps id '1' on playoff games), fall back to the latest
    completed post-season game, excluding the all-star game (id '4'). In every
    case the most recent qualifying game is the clincher.
    """
    completed = [
        e
        for e in events
        if ((_competition_of_event(e).get("status") or {}).get("type") or {}).get("state") == "post"
    ]
    if sport == "soccer":
        finals = [
            e
            for e in completed
            if ((e.get("season") or {}).get("slug") or "").lower() in _SOCCER_FINAL_SLUGS
        ]
    else:
        finals = [e for e in completed if _event_type_id(e) == "17"]
        if not finals:
            finals = [
                e
                for e in completed
                if ((e.get("season") or {}).get("slug") or "").lower() == "post-season"
                and _event_type_id(e) != _ALL_STAR_TYPE_ID
            ]
    if not finals:
        return None
    finals.sort(
        key=lambda e: (
            _parse_event_datetime(e.get("date") or "") or _dt.datetime.min.replace(tzinfo=_dt.UTC)
        )
    )
    return finals[-1]


def _champion_date_ranges(league_name: str, today: _dt.date) -> list[str]:
    """Scoreboard date ranges to search for the most recent completed final.

    For a league with a known championship window, yield the current year's
    window (clamped to today) then prior years — most recent first — so a
    just-concluded title is found before older ones, and a league whose current
    season hasn't finished falls back to the previous edition. Leagues without a
    window get a single recent look-back range.
    """
    window = _CHAMPIONSHIP_WINDOWS.get(league_name)
    if window is None:
        start = today - _dt.timedelta(days=_CHAMPION_FALLBACK_DAYS)
        return [f"{start:%Y%m%d}-{today:%Y%m%d}"]
    sm, sd, em, ed = window
    ranges: list[str] = []
    for year in (today.year, today.year - 1, today.year - 2):
        start = _dt.date(year, sm, sd)
        if start > today:
            continue  # this year's championship hasn't started
        end = min(_dt.date(year, em, ed), today)
        ranges.append(f"{start:%Y%m%d}-{end:%Y%m%d}")
    return ranges


async def get_champion(client: ESPNClient, competition: str) -> str:
    league = _resolve_competition(competition)
    if league is None:
        return CHAMPION_HELP

    today = _dt.datetime.now(_dt.UTC).date()
    championship = _CHAMPIONSHIP_NAMES.get(league.name, f"the {league.name} title")

    reached = False
    event = None
    for dates in _champion_date_ranges(league.name, today):
        try:
            data = await client.scoreboard(league.slug, dates=dates)
        except httpx.HTTPError as e:
            log.warning("champion scoreboard fetch failed: %s", e)
            continue
        reached = True
        event = _championship_event(data.get("events") or [], league.sport)
        if event is not None:
            break

    if not reached:
        return ESPN_UNREACHABLE
    if event is None:
        phrase = championship[:1].upper() + championship[1:]
        return f"{phrase} has not been decided yet."

    comp = _competition_of_event(event)
    competitors = comp.get("competitors", [])
    champ = next((c for c in competitors if c.get("winner")), None)
    if champ is None:
        champ = max(competitors, key=_competitor_score, default=None)
    opp = next((c for c in competitors if c is not champ), None)
    if champ is None or opp is None:
        phrase = championship[:1].upper() + championship[1:]
        return f"{phrase} has not been decided yet."

    return fmt.champion_line(
        champion=(champ.get("team") or {}).get("displayName") or "",
        championship=championship,
        opponent=(opp.get("team") or {}).get("displayName") or "",
        champ_score=_competitor_score(champ),
        opp_score=_competitor_score(opp),
        when=_parse_event_datetime(event.get("date") or ""),
    )


def _stat_value(entry: dict, name: str) -> int:
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return int(stat.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _detect_offseason(season_block: dict) -> bool:
    """Return True if season_block describes a season that has not yet started.

    Inspects season_block['season']['startDate']. If the date is in the
    future relative to UTC now, the league is considered to be in a
    pre-season or between-tournaments window. Returns False if the key
    is absent or unparseable (graceful fallback).

    Works for any ESPN response shape that carries 'season.startDate' at
    the top level of the passed dict — both the standings endpoint response
    and the scoreboard's leagues[0] block use this shape.
    """
    season = season_block.get("season") or {}
    start_iso = season.get("startDate") or ""
    if not start_iso:
        return False
    parsed = _parse_event_datetime(start_iso)
    if parsed is None:
        return False
    now = _dt.datetime.now(_dt.UTC)
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
    """Translate ESPN's 'clincher' stat into a qualification label.

    ESPN distinguishes three positive clinch states that all imply
    "qualified for the playoffs" but carry different leadership context:
        x = clinched a playoff berth (wild card or generic qualifier)
        y = clinched their division (top of their division)
        z = best record in conference / league
    'e' means eliminated. Anything else (rare codes like '*') yields None
    for the safe-fallback path.
    """
    for stat in entry.get("stats") or []:
        if stat.get("name") == "clincher":
            value = stat.get("displayValue") or ""
            if value == "x":
                return "qualified"
            if value == "y":
                return "division_winner"
            if value == "z":
                return "best_record"
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
    season = league_block.get("season") or {}
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


def _all_events_are_future(events: list[dict]) -> bool:
    """Return True if events is non-empty and every event is future-dated.

    "Future-dated" means the event's local-date is after today and its
    state is not "in" (in progress). Events whose date cannot be parsed
    are ignored. If no parseable future event exists, returns False.
    """
    if not events:
        return False
    now = _dt.datetime.now(_dt.UTC)
    today_local = now.astimezone().date()
    has_future = False
    for event in events:
        comp = _competition_of_event(event)
        status = comp.get("status", {})
        state = (status.get("type") or {}).get("state")
        if state == "in":
            return False
        when = _parse_event_datetime(event.get("date") or "")
        if when is None:
            continue
        event_local_date = when.astimezone().date()
        if event_local_date > today_local:
            has_future = True
        else:
            # An event today or earlier exists; not "all future".
            return False
    return has_future


def _upcoming_matches_phrase(events: list[dict], limit: int = 3) -> str:
    """Render 'Upcoming matches include X at Y on D, A at B on E.' (TTS-safe).

    Caps at limit events to keep the output listenable. Joins with Oxford-
    style 'and' for the last item.
    """
    pairs: list[str] = []
    for event in events:
        comp = _competition_of_event(event)
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home is None or away is None:
            continue
        when = _parse_event_datetime(event.get("date") or "")
        if when is None:
            continue
        date_str = fmt.date_phrase(when)
        team_pair = f"{away['team']['displayName']} at {home['team']['displayName']}"
        pairs.append(f"{team_pair} on {date_str}")
        if len(pairs) >= limit:
            break
    if not pairs:
        return "No upcoming matches found."
    if len(pairs) == 1:
        return f"Upcoming matches include {pairs[0]}."
    if len(pairs) == 2:
        return f"Upcoming matches include {pairs[0]} and {pairs[1]}."
    return f"Upcoming matches include {', '.join(pairs[:-1])}, and {pairs[-1]}."


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
        sentences.append(f"{away['team']['displayName']} at {home['team']['displayName']}, {tail}.")
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
    events = data.get("events") or []
    is_pre_tournament = _detect_offseason(league_block)

    if _all_events_are_future(events):
        upcoming = _upcoming_matches_phrase(events)
        if is_pre_tournament:
            return f"The {info.name} hasn't started yet. {upcoming}"
        return f"The {info.name} is in the {season_phrase}. {upcoming}"

    events_phrase = _events_phrase_for_status(events)
    return fmt.league_status_block(
        info.name,
        season_phrase,
        events_phrase,
        is_pre_tournament=is_pre_tournament,
    )
