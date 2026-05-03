from datetime import datetime, timezone

from sports_mcp.format import (
    clock_phrase,
    date_phrase,
    period_phrase_basketball,
    period_phrase_football,
    period_phrase_hockey,
    period_phrase_baseball,
    period_phrase_soccer,
    score_line,
    time_phrase,
    no_punctuation_artifacts,
)


def test_no_parens_or_slashes_helper():
    assert no_punctuation_artifacts("Hello world.") is True
    assert no_punctuation_artifacts("Foo (bar)") is False
    assert no_punctuation_artifacts("a/b") is False
    assert no_punctuation_artifacts("Tom & Jerry") is False
    assert no_punctuation_artifacts("vs. them") is False
    assert no_punctuation_artifacts("at @home") is False


def test_clock_phrase_minutes_and_seconds():
    assert clock_phrase("2:34") == "2 minutes 34 seconds remaining"


def test_clock_phrase_zero_minutes():
    assert clock_phrase("0:45") == "45 seconds remaining"


def test_clock_phrase_singular():
    assert clock_phrase("1:01") == "1 minute 1 second remaining"


def test_clock_phrase_empty():
    assert clock_phrase("") == ""
    assert clock_phrase(None) == ""


def test_period_phrase_basketball():
    assert period_phrase_basketball(1) == "first quarter"
    assert period_phrase_basketball(4) == "fourth quarter"
    assert period_phrase_basketball(5) == "overtime"
    assert period_phrase_basketball(6) == "double overtime"


def test_period_phrase_football_uses_quarter():
    assert period_phrase_football(2) == "second quarter"
    assert period_phrase_football(5) == "overtime"


def test_period_phrase_hockey():
    assert period_phrase_hockey(1) == "first period"
    assert period_phrase_hockey(3) == "third period"
    assert period_phrase_hockey(4) == "overtime"


def test_period_phrase_baseball_top_bottom():
    assert period_phrase_baseball(1, "top") == "top of the first inning"
    assert period_phrase_baseball(8, "bottom") == "bottom of the eighth inning"


def test_period_phrase_soccer():
    assert period_phrase_soccer(67) == "minute 67"


def test_score_line_basic():
    s = score_line(
        away_name="Lakers",
        away_score=89,
        home_name="Celtics",
        home_score=91,
        period_text="fourth quarter",
        clock_text="2 minutes 34 seconds remaining",
    )
    assert s == "Lakers 89, Celtics 91, fourth quarter, 2 minutes 34 seconds remaining."
    assert no_punctuation_artifacts(s)


def test_score_line_no_clock():
    s = score_line(
        away_name="Yankees",
        away_score=4,
        home_name="Red Sox",
        home_score=2,
        period_text="top of the eighth inning",
        clock_text="",
    )
    assert s == "Yankees 4, Red Sox 2, top of the eighth inning."


def test_time_phrase_eastern_pm():
    # 8:00 PM eastern (UTC -4 during DST: 24:00Z; check non-DST too)
    dt = datetime(2026, 5, 8, 20, 0, tzinfo=timezone.utc)
    s = time_phrase(dt)
    # Result depends on host timezone; assert format only
    assert "PM" in s or "AM" in s
    assert no_punctuation_artifacts(s)


def test_time_phrase_no_minutes_when_on_hour():
    # Build a local-time anchored datetime: 8:00 PM local
    import datetime as _dt
    local = _dt.datetime(2026, 5, 8, 20, 0).astimezone()
    s = time_phrase(local)
    assert s == "8 PM"


def test_time_phrase_with_minutes():
    import datetime as _dt
    local = _dt.datetime(2026, 5, 8, 19, 30).astimezone()
    s = time_phrase(local)
    assert s == "7 30 PM"


def test_date_phrase_today(monkeypatch):
    import datetime as _dt
    fixed_now = _dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    same_day = _dt.datetime(2026, 5, 8, 20, 0).astimezone()
    assert date_phrase(same_day) == "today"


def test_date_phrase_tomorrow(monkeypatch):
    import datetime as _dt
    fixed_now = _dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    next_day = _dt.datetime(2026, 5, 9, 20, 0).astimezone()
    assert date_phrase(next_day) == "tomorrow"


def test_date_phrase_weekday_within_week(monkeypatch):
    import datetime as _dt
    fixed_now = _dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    in_5_days = _dt.datetime(2026, 5, 13, 20, 0).astimezone()
    # 2026-05-13 is a Wednesday
    assert date_phrase(in_5_days) == "Wednesday"


def test_date_phrase_calendar_date_beyond_week(monkeypatch):
    import datetime as _dt
    fixed_now = _dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    in_15_days = _dt.datetime(2026, 5, 23, 20, 0).astimezone()
    assert date_phrase(in_15_days) == "May 23"
