# `get_live_score` Completed and Scheduled Games — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `get_live_score` so it returns a TTS-safe outcome narrative for completed games (`state == "post"`) and a TTS-safe pre-game line for scheduled-today games (`state == "pre"`), instead of the current flat "no live game" answer.

**Architecture:** Add two pure formatters to `sports_mcp/format.py` (`final_outcome_line`, `pre_game_line`). Reshape the state-branch block in `get_live_score` to call the appropriate formatter for each state. Existing helpers (`_parse_event_datetime`, alias resolution, ESPN fetch, error handling) are unchanged.

**Tech Stack:** Python 3.13, existing `httpx` mocks via `pytest-asyncio`. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-05-02-live-score-completed-and-scheduled-design.md](../specs/2026-05-02-live-score-completed-and-scheduled-design.md)

---

## File Structure

Files modified by this plan:

- **`sports_mcp/format.py`** (modify): append two new pure functions, `final_outcome_line` and `pre_game_line`. ~30 lines added.
- **`sports_mcp/tools.py`** (modify): replace the body of `get_live_score` after the existing `state` extraction line. The non-`"in"` early return becomes three branches (`"post"`, `"pre"`, fall-through). ~30 lines changed.
- **`tests/test_format.py`** (modify): append 6 unit tests covering win/loss/tie + away/home.
- **`tests/test_tools.py`** (modify): append 3 integration tests for `get_live_score` post-win, post-loss, and pre paths.

No files are created. No existing tests are removed or modified — `test_get_live_score_no_live_game` continues to pass because its payload has no `date` field, which makes the new pre branch's date parser return `None` and fall through to the existing flat-string path.

---

## Task 1: `final_outcome_line` formatter

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `tests/test_format.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_format.py`:

```python
from sports_mcp.format import final_outcome_line


def test_final_outcome_line_win():
    s = final_outcome_line(
        team_name="Los Angeles Lakers",
        team_score=91,
        opp_name="Boston Celtics",
        opp_score=89,
    )
    assert s == "The Los Angeles Lakers beat the Boston Celtics 91 to 89."
    assert no_punctuation_artifacts(s)


def test_final_outcome_line_loss():
    s = final_outcome_line(
        team_name="Los Angeles Lakers",
        team_score=89,
        opp_name="Boston Celtics",
        opp_score=91,
    )
    assert s == "The Los Angeles Lakers lost to the Boston Celtics 89 to 91."
    assert no_punctuation_artifacts(s)


def test_final_outcome_line_tie():
    s = final_outcome_line(
        team_name="Arsenal",
        team_score=1,
        opp_name="Chelsea",
        opp_score=1,
    )
    assert s == "The Arsenal and the Chelsea tied 1 to 1."
    assert no_punctuation_artifacts(s)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py::test_final_outcome_line_win -v
```

Expected: ImportError or AttributeError — `final_outcome_line` is not yet defined.

- [ ] **Step 3: Implement `final_outcome_line`**

Append to `sports_mcp/format.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: all format tests pass (29 prior + 3 new = 32).

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Add final_outcome_line formatter for completed games"
```

---

## Task 2: `pre_game_line` formatter

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `tests/test_format.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_format.py`:

```python
import datetime as _test_dt

from sports_mcp.format import pre_game_line


def test_pre_game_line_away(monkeypatch):
    fixed_now = _test_dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    when = _test_dt.datetime(2026, 5, 8, 19, 30).astimezone()
    s = pre_game_line(
        team_name="Los Angeles Lakers",
        opp_name="Boston Celtics",
        when=when,
        is_home=False,
    )
    assert s == (
        "The Los Angeles Lakers don't have a live game yet. "
        "They play the Boston Celtics today at 7 30 PM."
    )
    assert no_punctuation_artifacts(s)


def test_pre_game_line_home(monkeypatch):
    fixed_now = _test_dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    when = _test_dt.datetime(2026, 5, 8, 20, 0).astimezone()
    s = pre_game_line(
        team_name="Los Angeles Lakers",
        opp_name="Boston Celtics",
        when=when,
        is_home=True,
    )
    assert s == (
        "The Los Angeles Lakers don't have a live game yet. "
        "They host the Boston Celtics today at 8 PM."
    )
    assert no_punctuation_artifacts(s)


def test_pre_game_line_tomorrow(monkeypatch):
    fixed_now = _test_dt.datetime(2026, 5, 8, 12, 0).astimezone()
    monkeypatch.setattr("sports_mcp.format._now_local", lambda: fixed_now)
    when = _test_dt.datetime(2026, 5, 9, 19, 30).astimezone()
    s = pre_game_line(
        team_name="Los Angeles Lakers",
        opp_name="Boston Celtics",
        when=when,
        is_home=False,
    )
    assert s == (
        "The Los Angeles Lakers don't have a live game yet. "
        "They play the Boston Celtics tomorrow at 7 30 PM."
    )
    assert no_punctuation_artifacts(s)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py::test_pre_game_line_away -v
```

Expected: ImportError or AttributeError — `pre_game_line` is not yet defined.

- [ ] **Step 3: Implement `pre_game_line`**

Append to `sports_mcp/format.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: 32 prior + 3 new = 35 tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Add pre_game_line formatter for scheduled-today games"
```

---

## Task 3: Reshape `get_live_score` state branching

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
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
    # The exact time string depends on host timezone; assert the structural pieces.
    assert "Los Angeles Lakers don't have a live game yet" in s
    assert "play the Boston Celtics" in s
    assert "PM" in s or "AM" in s
    assert "(" not in s and ")" not in s
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_live_score_post_state_win -v
```

Expected: FAIL — current behavior returns `"The Los Angeles Lakers do not have a live game right now."`

- [ ] **Step 3: Reshape `get_live_score` body**

In `sports_mcp/tools.py`, replace the block from line 110 to line 129 (the existing `if state != "in":` early-return through the existing `return fmt.score_line(...)`) with the new state-branching block.

Find this exact block:

```python
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
```

Replace it with:

```python
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
```

Key differences from the original block:
- The competitor extraction (home/away/None-check) moves up before the state branches, because all three states need it.
- New `is_home`, `team_competitor`, `opp_competitor` derivations.
- New `state == "post"` branch returns `final_outcome_line`.
- New `state == "pre"` branch returns `pre_game_line` if the event has a parseable date; falls back to the flat string if not.
- The fall-through `if state != "in"` flat-string return is preserved for any other unexpected state.
- The live-game branch (the existing `score_line` return) is unchanged.

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 17 prior + 3 new = 20 tool tests pass.

If `test_get_live_score_no_live_game` fails (it should not), inspect the test payload — it should use `state == "pre"` with no `date` field, which routes through the new pre branch's `_parse_event_datetime("") → None → fall-through` path. If the test fails, the cause is likely a typo in the new branching block, not a problem with the test itself.

- [ ] **Step 5: Run full suite as a sanity check**

```bash
uv run pytest -q
```

Expected: 77 prior + 6 new = 83 tests pass total.

- [ ] **Step 6: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Surface completed and scheduled games in get_live_score"
```

---

## Task 4: Final integration check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: 83 tests pass.

- [ ] **Step 2: Sanity-check the new behavior end to end against the live API**

```bash
uv run python -c "
import asyncio
from sports_mcp.espn import ESPNClient
from sports_mcp.tools import get_live_score

async def main():
    c = ESPNClient()
    try:
        for team in ('Lakers', 'Yankees', 'Arsenal'):
            print(f'{team}: {await get_live_score(c, team)}')
    finally:
        await c.aclose()

asyncio.run(main())
"
```

Expected: each line prints one of the three response shapes:
- "The Los Angeles Lakers beat the Boston Celtics 110 to 105."
- "The Los Angeles Lakers don't have a live game yet. They play the Boston Celtics today at 8 PM."
- "Lakers 89, Celtics 91, fourth quarter, 2 minutes 34 seconds remaining." (live game)
- "The Los Angeles Lakers do not have a live game right now." (no event today)

The exact output depends on what's happening in real ESPN at runtime. Verify each printed string is TTS-safe (no parens, slashes, ampersands, abbreviations like "vs.", "@", "ET", or score-style hyphens).

- [ ] **Step 3: Done**

No commit needed for Task 4.
