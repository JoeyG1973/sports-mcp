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
