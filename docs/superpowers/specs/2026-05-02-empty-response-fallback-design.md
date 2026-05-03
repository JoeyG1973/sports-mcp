# Empty Response Fallback

**Date:** 2026-05-02
**Status:** Draft, pending user review

## Summary

This change strengthens the response-quality contract of the four tool
functions in three small ways: a bug fix for a redundant `"scheduled
Scheduled"` phrasing surfaced in live World Cup output, a regression-guard
test layer asserting no tool ever returns an empty string, and a tailored
fallback for `get_league_status` when a tournament-format competition (the
World Cup, primarily) has no current events.

## Motivation

A live audit of the four tools surfaced one concrete bug and one quality
gap:

1. **`scheduled Scheduled` duplication.** `get_league_status("World Cup")`
   currently returns `"The World Cup is in the group stage. South Africa
   at Mexico, scheduled Scheduled. Czechia at South Korea, scheduled
   Scheduled."`. The `_events_phrase_for_status` helper composes
   `f"scheduled {short}"` where `short` is ESPN's `shortDetail` field. For
   pre-state events ESPN often supplies the literal word `"Scheduled"`,
   producing the duplicated phrase. Reads poorly through TTS.

2. **Generic fallback for tournament-format leagues.** When the events
   list is empty for the World Cup or Champions League outside their
   competition windows, `get_league_status` returns
   `"The {league} is in the offseason. No games today."`. The "offseason"
   framing is right for the NFL but misleading for tournament cycles —
   the World Cup is in offseason most of the time *between* tournaments.
   A better phrasing acknowledges that.

The user's broader concern is that no tool should ever return an empty
string. A code audit confirmed no current path returns `""`, but a
regression-guard test layer is cheap and protects against future
breakage.

## Goals

- Eliminate the `"scheduled Scheduled"` duplication.
- Replace the generic `"No games today."` fallback with a
  tournament-aware message when the league is between tournaments.
- Add a test layer that asserts none of the four tools returns an empty
  string under a battery of edge-case inputs.

## Non-goals

- No changes to `get_live_score`, `get_next_game`, or `get_standings`
  output other than the new regression-guard tests.
- No new tools, no new ESPN endpoints, no new dependencies.
- No bulk renaming of the existing fallback message
  (`"No games today."`) for non-tournament leagues — it reads correctly
  for NFL/NBA/MLB/NHL/EPL/MLS in their respective offseasons. Only
  tournament-format leagues get the new phrasing.
- No fix for the pre-existing `"Brighton & Hove Albion"` ampersand leak
  in standings output. That is a separate team-name sanitization issue
  that pre-dates this work.

## Detail per change

### Change 1 — `scheduled Scheduled` fix

In `sports_mcp/tools.py:_events_phrase_for_status`, the current `else`
branch:

```python
else:
    tail = f"scheduled {short}".strip()
```

is replaced with:

```python
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
- `short = "7 30 PM eastern"` (already sanitized by `_sanitize_short_detail`) → `tail = "scheduled 7 30 PM eastern"` (unchanged).

### Change 2 — Tournament-aware fallback in `get_league_status`

`fmt.league_status_block` gains a third optional parameter:

```python
def league_status_block(
    league_name: str,
    season_phrase: str,
    events_phrase: str,
    is_pre_tournament: bool = False,
) -> str:
    head = f"The {league_name} is in the {season_phrase}."
    if events_phrase.strip():
        body = events_phrase.strip()
    elif is_pre_tournament:
        body = "No current events. The tournament may not have started yet."
    else:
        body = "No games today."
    return f"{head} {body}"
```

`get_league_status` in `sports_mcp/tools.py` derives `is_pre_tournament`
from the scoreboard's season block via the existing `_detect_offseason`
helper:

```python
leagues = data.get("leagues") or []
league_block = leagues[0] if leagues else {}
season_phrase = _season_phrase(league_block)
events_phrase = _events_phrase_for_status(data.get("events") or [])
is_pre_tournament = _detect_offseason(league_block)
return fmt.league_status_block(
    info.name, season_phrase, events_phrase, is_pre_tournament
)
```

`_detect_offseason` was originally written for the standings endpoint;
its logic (`season.startDate > today`) is generic and applies equally to
the scoreboard's `leagues[0].season` block. Same key path, same
semantics.

The fallback fires only when `events_phrase` is empty *and*
`is_pre_tournament` is `True`. For the NFL in offseason, the scoreboard
returns events (last season's games or upcoming preseason), so
`events_phrase` is non-empty and the new branch never fires — NFL keeps
its current behavior.

For the World Cup outside a tournament window, the scoreboard returns
no events and `season.startDate` is in the future → fallback fires:
`"The World Cup is in the offseason. No current events. The tournament
may not have started yet."`.

### Change 3 — Regression-guard tests

A single new test in `tests/test_tools.py` exercises every fallback path
and asserts each result is non-empty:

```python
async def test_no_tool_returns_empty_string():
    """Regression guard: no tool may return an empty string. Every fallback
    path must produce a TTS-safe natural-language message.
    """
    cases = [
        ("get_live_score", "Quidditch United"),         # unknown team
        ("get_next_game", "Quidditch United"),          # unknown team
        ("get_standings", "Quidditch"),                 # unknown league
        ("get_league_status", "Quidditch"),             # unknown league
    ]
    # plus per-tool tests with empty payload from a working ESPN response
    # plus per-tool tests with httpx raising
```

The assertion shape: `assert s != ""` and `assert no_punctuation_artifacts(s)`
for each case. Approximately 12 assertions across 6 sub-tests. Failures
indicate either a real empty-string regression or an unintended TTS leak.

## Code organization

- **`sports_mcp/format.py`** — extend `league_status_block` with the new
  `is_pre_tournament` keyword-only parameter.
- **`sports_mcp/tools.py`** — fix `_events_phrase_for_status`; pass
  `is_pre_tournament` through `get_league_status`.
- **`tests/test_format.py`** — extend tests for `league_status_block`
  covering the new branch.
- **`tests/test_tools.py`** — add the regression-guard test for the four
  tools; add a test for the `scheduled Scheduled` fix; add a test for the
  pre-tournament fallback in `get_league_status`.

No new files. No public API breakage; the new `league_status_block`
parameter is keyword-only with a `False` default.

## Testing

### `tests/test_format.py`

- `test_league_status_block_pre_tournament_with_no_events` — empty
  `events_phrase`, `is_pre_tournament=True`. Output ends with
  `"No current events. The tournament may not have started yet."`.
- `test_league_status_block_pre_tournament_with_events` — non-empty
  `events_phrase`, `is_pre_tournament=True`. The pre-tournament fallback
  does NOT fire (events_phrase wins). Output unchanged from existing
  behavior.
- `test_league_status_block_no_pre_tournament_default` — keyword omitted
  defaults to `False`. Existing behavior preserved.

### `tests/test_tools.py`

- `test_get_league_status_scheduled_no_short_detail` — fixture with one
  pre-state event whose `shortDetail` is `"Scheduled"`. Output contains
  `"scheduled."` (lowercase, no duplication) and does NOT contain
  `"scheduled Scheduled"`.
- `test_get_league_status_world_cup_pre_tournament_fallback` — fixture
  with empty `events` and `leagues[0].season.startDate` in the future.
  Output ends with `"No current events. The tournament may not have
  started yet."`.
- `test_no_tool_returns_empty_string` — described above.

### Existing tests

`test_get_league_status_in_season_with_games` and the rest continue to
pass. The fixture for the in-season test uses
`status.type.shortDetail == "7:30 PM ET"`, which after sanitization
becomes `"7 30 PM eastern"`. That is non-empty and not equal to
`"Scheduled"`, so it routes through the unchanged `else` branch and
produces `"...scheduled 7 30 PM eastern."` — same as today.

## Risks

- **`_detect_offseason` reused across endpoints.** The function is
  generic over its input shape (looks up `season.startDate`). Both the
  standings response (top level) and the scoreboard response
  (`leagues[0]`) carry that path. The reuse is safe; if either endpoint
  ever drops `season.startDate`, the function returns `False` (graceful
  fallback).
- **Pre-tournament detection might fire when it shouldn't.** If ESPN
  ever populates `season.startDate` with a future date for an actively
  running tournament (a data inconsistency observed during the audit
  for the World Cup standings endpoint), the fallback message would
  still be off. Mitigation: the fallback only fires when
  `events_phrase` is empty. Once events exist, the unchanged branch
  takes over. The combined condition is conservative.
- **`scheduled Scheduled` not the only ESPN sentinel.** ESPN may use
  other status-text duplications. We fix the one observed in production
  data; future ones surface via the regression-guard tests if they
  produce empty or duplicate output.
