# Empty-Response Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `"scheduled Scheduled"` duplication, add a tournament-aware fallback for `get_league_status` when no current events exist for a between-tournaments league, and add regression-guard tests asserting no tool returns an empty string.

**Architecture:** Three small, independent changes — one bug fix in a private helper in `tools.py`, one optional kwarg added to a formatter in `format.py` and threaded through one tool function, and one defensive test that loops over fallback paths.

**Tech Stack:** Python 3.13, `httpx` mocks via `pytest-asyncio`. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-05-02-empty-response-fallback-design.md](../specs/2026-05-02-empty-response-fallback-design.md)

---

## File Structure

Files modified by this plan:

- **`sports_mcp/tools.py`** — fix `_events_phrase_for_status` (Task 1); thread `is_pre_tournament` through `get_league_status` (Task 2). ~10 lines changed.
- **`sports_mcp/format.py`** — extend `league_status_block` with the new keyword-only parameter (Task 2). ~10 lines changed.
- **`tests/test_format.py`** — add 3 tests for the new `league_status_block` branch (Task 2). ~30 lines added.
- **`tests/test_tools.py`** — add 1 test for the `scheduled Scheduled` fix (Task 1), 1 test for the pre-tournament fallback (Task 2), and 1 regression-guard sweep (Task 3). ~80 lines added.

No files are created. No public API breakage; the new `league_status_block` parameter is keyword-only with a `False` default.

---

## Task 1: Fix `scheduled Scheduled` duplication

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write a failing test**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run test and verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_league_status_scheduled_no_short_detail -v
```

Expected: FAIL — current output contains `"scheduled Scheduled."`

- [ ] **Step 3: Fix `_events_phrase_for_status`**

In `sports_mcp/tools.py`, find the existing `_events_phrase_for_status` function. The relevant part is the per-event tail computation:

```python
        if state == "in":
            tail = "in progress"
        elif state == "post":
            tail = "final"
        else:
            tail = f"scheduled {short}".strip()
```

Replace the `else` branch with:

```python
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
```

This handles three cases:
- `short = ""` (ESPN omitted shortDetail) → `tail = "scheduled"`.
- `short = "Scheduled"` (ESPN literal default for pre-state) → `tail = "scheduled"` (lowercase, no duplication).
- `short = "7 30 PM eastern"` (already sanitized by `_sanitize_short_detail`) → `tail = "scheduled 7 30 PM eastern"`.

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 33 prior + 1 new = 34 tool tests pass. The existing `test_get_league_status_in_season_with_games` test continues to pass — its `shortDetail` is `"7:30 PM ET"`, which `_sanitize_short_detail` converts to `"7 30 PM eastern"`. That is non-empty and not equal to `"scheduled"`, so it routes through the unchanged-behavior third sub-branch and produces `"...scheduled 7 30 PM eastern."` in the output, the same as before this change.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Fix scheduled Scheduled duplication in events phrase"
```

---

## Task 2: Tournament-aware fallback in `get_league_status`

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_format.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests for the new format branch**

Append to `tests/test_format.py`:

```python
def test_league_status_block_pre_tournament_with_no_events():
    s = league_status_block(
        "World Cup",
        season_phrase="offseason",
        events_phrase="",
        is_pre_tournament=True,
    )
    assert s == (
        "The World Cup is in the offseason. "
        "No current events. The tournament may not have started yet."
    )
    assert no_punctuation_artifacts(s)


def test_league_status_block_pre_tournament_with_events():
    """When events exist, the events_phrase wins regardless of is_pre_tournament."""
    s = league_status_block(
        "World Cup",
        season_phrase="group stage",
        events_phrase="Mexico at Canada, scheduled.",
        is_pre_tournament=True,
    )
    assert s == "The World Cup is in the group stage. Mexico at Canada, scheduled."


def test_league_status_block_no_pre_tournament_default():
    """is_pre_tournament defaults to False; existing callers unaffected."""
    s = league_status_block(
        "NBA",
        season_phrase="regular season, week 12",
        events_phrase="",
    )
    assert s == "The NBA is in the regular season, week 12. No games today."
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py::test_league_status_block_pre_tournament_with_no_events -v
```

Expected: FAIL — `league_status_block` does not yet accept `is_pre_tournament`.

- [ ] **Step 3: Extend `league_status_block`**

In `sports_mcp/format.py`, find this existing function:

```python
def league_status_block(
    league_name: str,
    season_phrase: str,
    events_phrase: str,
) -> str:
    """Combine season context and today's slate into one TTS-safe paragraph."""
    head = f"The {league_name} is in the {season_phrase}."
    body = events_phrase.strip() if events_phrase else "No games today."
    return f"{head} {body}"
```

Replace with:

```python
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
```

Two changes from the original:
- New keyword-only `is_pre_tournament: bool = False` parameter (after `*`).
- Body selection becomes a three-way branch: events_phrase wins; otherwise pre-tournament fallback; otherwise the existing default.

- [ ] **Step 4: Run format tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: 42 prior + 3 new = 45 format tests pass.

- [ ] **Step 5: Write a failing tool test for the pre-tournament fallback**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 6: Run the new tool test and verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_league_status_world_cup_pre_tournament_fallback -v
```

Expected: FAIL — `get_league_status` doesn't yet pass `is_pre_tournament` through.

- [ ] **Step 7: Thread `is_pre_tournament` through `get_league_status`**

In `sports_mcp/tools.py`, find this existing function:

```python
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
    return fmt.league_status_block(info.name, season_phrase, events_phrase)
```

Replace with:

```python
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
```

Two changes:
- New `is_pre_tournament` derivation via `_detect_offseason(league_block)`. The function was originally written for the standings response, but its logic — `season.startDate > today` — is generic. The scoreboard's `leagues[0]` block has the same `season.startDate` shape, so reuse is safe.
- The `league_status_block` call passes the kwarg. Other callers (none currently exist outside this function, but the kwarg-only design protects future ones) are unaffected.

- [ ] **Step 8: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 34 prior + 1 new = 35 tool tests pass. Existing `test_get_league_status_in_season_with_games`, `test_get_league_status_no_games`, and `test_get_league_status_scheduled_event_has_no_colon_or_et` continue to pass — their fixtures lack a `season.startDate` block, so `_detect_offseason` returns `False` and the new fallback never fires.

- [ ] **Step 9: Commit**

```bash
git add sports_mcp/format.py sports_mcp/tools.py tests/test_format.py tests/test_tools.py
git commit -m "Add tournament-aware fallback to get_league_status"
```

---

## Task 3: Regression-guard sweep

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the regression-guard test**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 35 prior + 9 new (4 unknown-input parametrized + 4 unreachable parametrized + 1 minimal-payload) = 44 tool tests pass.

If any of the new sub-tests fails, that means a real empty-string regression was uncovered. Investigate before moving on.

The `import pytest` at the top of the new block is fine even if `pytest` is already imported elsewhere in the file (Python's import system makes the duplicate a no-op). If a top-of-file `import pytest` already exists, the local import is harmless; if it doesn't, this line provides it.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tools.py
git commit -m "Add regression-guard tests asserting no tool returns empty"
```

---

## Task 4: Final integration check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -q
```

Expected: 105 prior + 1 (Task 1) + 3 + 1 (Task 2) + 9 (Task 3) = 119 tests pass.

- [ ] **Step 2: Live ESPN sanity probe**

```bash
uv run python -c "
import asyncio
from sports_mcp.espn import ESPNClient
from sports_mcp.tools import get_league_status

async def main():
    c = ESPNClient()
    try:
        for league in ('World Cup', 'Champions League', 'NBA', 'NFL'):
            s = await get_league_status(c, league)
            print(f'{league}: {s[:300]}')
            print()
    finally:
        await c.aclose()

asyncio.run(main())
"
```

Expected behavior at run time:

- **World Cup**: response no longer contains `"scheduled Scheduled"`. If currently between tournaments (no events), output ends with `"No current events. The tournament may not have started yet."`. If group-stage events exist, each is `"... scheduled."` (lowercase, single).
- **Champions League**: same — no `"scheduled Scheduled"`.
- **NBA / NFL**: unchanged behavior. `"scheduled 7 30 PM eastern"` style is preserved.

- [ ] **Step 3: Done**

No commit needed for Task 4.
