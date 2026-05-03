"""TTS-safe formatters and helpers.

All public functions return strings safe to read aloud: no parentheses,
slashes, ampersands, abbreviations, or score-style hyphens.
"""
from __future__ import annotations

import datetime as _dt

_FORBIDDEN_SUBSTRINGS = ("(", ")", "/", "&", "vs.", "@")


def no_punctuation_artifacts(text: str) -> bool:
    """Return True if text contains none of the TTS-unsafe substrings."""
    return not any(s in text for s in _FORBIDDEN_SUBSTRINGS)


_ORDINAL_WORDS = [
    "zeroth",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
]


def ordinal_word(n: int) -> str:
    """Return the English ordinal word for small n; falls back to 'Nth'."""
    if 0 <= n < len(_ORDINAL_WORDS):
        return _ORDINAL_WORDS[n]
    return f"{n}th"


def clock_phrase(clock: str | None) -> str:
    """Convert M:SS clock string to 'M minutes S seconds remaining'."""
    if not clock:
        return ""
    parts = clock.split(":")
    if len(parts) != 2:
        return ""
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except ValueError:
        return ""
    pieces: list[str] = []
    if minutes:
        unit = "minute" if minutes == 1 else "minutes"
        pieces.append(f"{minutes} {unit}")
    if seconds or not pieces:
        unit = "second" if seconds == 1 else "seconds"
        pieces.append(f"{seconds} {unit}")
    return " ".join(pieces) + " remaining"


def _quarter_or_overtime(period: int) -> str:
    if 1 <= period <= 4:
        return f"{ordinal_word(period)} quarter"
    if period == 5:
        return "overtime"
    return f"{ordinal_word(period - 4)} overtime" if period == 6 else f"overtime period {period - 4}"


def period_phrase_basketball(period: int) -> str:
    if period == 6:
        return "double overtime"
    return _quarter_or_overtime(period)


def period_phrase_football(period: int) -> str:
    if period == 5:
        return "overtime"
    return _quarter_or_overtime(period)


def period_phrase_hockey(period: int) -> str:
    if 1 <= period <= 3:
        return f"{ordinal_word(period)} period"
    if period == 4:
        return "overtime"
    return f"overtime period {period - 3}"


def period_phrase_baseball(inning: int, half: str) -> str:
    return f"{half} of the {ordinal_word(inning)} inning"


def period_phrase_soccer(minute: int) -> str:
    return f"minute {minute}"


def score_line(
    away_name: str,
    away_score: int,
    home_name: str,
    home_score: int,
    period_text: str,
    clock_text: str,
) -> str:
    """Compose a TTS-safe score line.

    Format: '<away> <s>, <home> <s>, <period>[, <clock>].'
    """
    base = f"{away_name} {away_score}, {home_name} {home_score}, {period_text}"
    if clock_text:
        base = f"{base}, {clock_text}"
    return base + "."


def _now_local() -> _dt.datetime:
    """Return the current local datetime; isolated for monkeypatching in tests."""
    return _dt.datetime.now().astimezone()


def time_phrase(when: _dt.datetime) -> str:
    """Convert a datetime (any tz) to local-time prose like '8 PM' or '7 30 PM'."""
    local = when.astimezone()
    hour = local.hour
    minute = local.minute
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    if minute == 0:
        return f"{display_hour} {suffix}"
    return f"{display_hour} {minute} {suffix}"


def date_phrase(when: _dt.datetime) -> str:
    """Convert a datetime to a TTS-safe date phrase relative to now.

    today / tomorrow within the next two days; weekday name within the
    next week; 'Month D' beyond that.
    """
    local = when.astimezone()
    now = _now_local()
    today = now.date()
    delta_days = (local.date() - today).days
    if delta_days == 0:
        return "today"
    if delta_days == 1:
        return "tomorrow"
    if 2 <= delta_days < 7:
        return local.strftime("%A")
    return local.strftime("%B %-d")


def _join_with_or(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return ", ".join(items[:-1]) + ", or " + items[-1]


def standings_block(label: str, rows: list[dict]) -> str:
    """Render a standings table as TTS-safe prose.

    Each row is a dict with 'name', 'wins', 'losses'. Optional 'ties' key.
    Optional 'qualification' key, one of 'qualified' or 'eliminated', adds
    a playoff-qualification annotation to that row.
    """
    if not rows:
        return f"{label} standings are not available."
    parts = [f"{label}."]
    for i, row in enumerate(rows, start=1):
        rank = ordinal_word(i)
        wins = row["wins"]
        losses = row["losses"]
        wins_word = "win" if wins == 1 else "wins"
        losses_word = "loss" if losses == 1 else "losses"
        sentence = (
            f"{row['name']} {rank} at {wins} {wins_word} and {losses} {losses_word}"
        )
        qualification = row.get("qualification")
        if qualification == "qualified":
            sentence += ", qualified for the playoffs"
        elif qualification == "eliminated":
            sentence += ", did not qualify for the playoffs"
        parts.append(sentence + ".")
    text = " ".join(parts)
    # Trim final period so we can re-add it cleanly with no double periods.
    return text.rstrip(".") + "."


def league_status_block(
    league_name: str,
    season_phrase: str,
    events_phrase: str,
    *,
    is_pre_tournament: bool = False,
) -> str:
    """Combine season context and today's slate into one TTS-safe paragraph.

    When events_phrase is empty and is_pre_tournament is True, use a
    tournament-aware fallback message instead of the default
    "No games today.". This matches the expected wording for between-
    tournaments leagues like the World Cup.
    """
    head = f"The {league_name} is in the {season_phrase}."
    if events_phrase.strip():
        body = events_phrase.strip()
    elif is_pre_tournament:
        body = "No current events. The tournament may not have started yet."
    else:
        body = "No games today."
    return f"{head} {body}"


def ambiguity_message(team_text: str, candidates: list[str]) -> str:
    """Compose 'X is ambiguous. Did you mean A, B, or C?' for 2 or more options."""
    return f"{team_text} is ambiguous. Did you mean {_join_with_or(candidates)}?"


def unknown_team_message(team_text: str, suggestions: list[str]) -> str:
    """Compose 'I don't recognize X[. Did you mean ...]?' as TTS-safe prose."""
    if not suggestions:
        return f"I don't recognize {team_text}."
    return f"I don't recognize {team_text}. Did you mean {_join_with_or(suggestions)}?"


def unknown_league_message(league_text: str, suggestions: list[str]) -> str:
    if not suggestions:
        return f"I don't recognize {league_text}."
    return f"I don't recognize {league_text}. Did you mean {_join_with_or(suggestions)}?"


def final_outcome_line(
    team_name: str,
    team_score: int,
    opp_name: str,
    opp_score: int,
) -> str:
    """Compose a TTS-safe final-score narrative from team_name's perspective.

    The queried team's score is always spoken first.

    Examples:
        win:  "The Lakers beat the Celtics 91 to 89."
        loss: "The Lakers lost to the Celtics 89 to 91."
        tie:  "The Lakers and the Celtics tied 1 to 1."
    """
    if team_score > opp_score:
        return f"The {team_name} beat the {opp_name} {team_score} to {opp_score}."
    if team_score < opp_score:
        return f"The {team_name} lost to the {opp_name} {team_score} to {opp_score}."
    return f"The {team_name} and the {opp_name} tied {team_score} to {opp_score}."


def pre_game_line(
    team_name: str,
    opp_name: str,
    when: _dt.datetime,
    is_home: bool,
) -> str:
    """Compose a TTS-safe pre-game line for a game scheduled later today.

    Names the opponent and the local-time tip-off. "host" if the queried
    team is the home team, "play" otherwise. Venue is intentionally omitted.
    """
    verb = "host" if is_home else "play"
    date_str = date_phrase(when)
    time_str = time_phrase(when)
    return (
        f"The {team_name} don't have a live game yet. "
        f"They {verb} the {opp_name} {date_str} at {time_str}."
    )


def season_phase_prefix(league_name: str, phase: str) -> str:
    """Return the phase-announcement prefix for a get_standings response.

    phase is one of 'regular', 'postseason', 'offseason'. Anything else
    yields an empty prefix.
    """
    if phase == "offseason":
        return f"The {league_name} is in the offseason. Last season. "
    if phase == "postseason":
        return f"The {league_name} is in the playoffs. "
    return ""
