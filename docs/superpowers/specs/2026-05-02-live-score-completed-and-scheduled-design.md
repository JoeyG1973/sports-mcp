# `get_live_score` — surface completed and scheduled games

**Date:** 2026-05-02
**Status:** Draft, pending user review
**Supersedes / extends:** [2026-05-02 sports-mcp design](2026-05-02-sports-mcp-design.md)

## Summary

`get_live_score` currently returns a flat `"do not have a live game right
now"` whenever the scoreboard event for the queried team is not in the
`"in"` state. This hides useful information that ESPN already supplies:
final scores for games that ended earlier today, and tip-off times for
games scheduled later today. This change extends `get_live_score` to
distinguish three states — live, final, scheduled — each with a TTS-safe
response that directly answers the most natural questions a Home Assistant
voice user asks ("did they win?", "are they playing?", "is the game on?").

## Motivation

In real use, the most common live-score voice queries are:

1. "Did the Lakers win?" — asked any time after a game ends.
2. "What's the Lakers score?" — asked during a game.
3. "Are the Lakers playing tonight?" — asked before a game starts.

Today, only (2) gets a useful answer. Cases (1) and (3) both hit the
"no live game" branch even though ESPN's scoreboard payload already
contains the final score (1) or the scheduled time (3). The data is one
field-read away from the user's question.

## Goals

- For `state == "post"`, return a TTS-safe outcome narrative from the
  queried team's perspective.
- For `state == "pre"`, return a TTS-safe pre-game line that names the
  opponent and the local-time tip-off.
- Preserve the live-game branch unchanged.
- Preserve the "no event for this team in today's scoreboard" branch
  unchanged.
- Keep both new branches reusable as named formatters in `format.py`.
- Cover both new branches with unit tests at the formatter and tool levels.

## Non-goals

- No new tools, no new dependencies, no new ESPN endpoints.
- No tool rename. `get_live_score` stays the public name; the natural
  language in the response distinguishes the three states.
- No OT/shootout suffix on final scores in this iteration. The score is
  reported as-is; if the user needs that detail, add later.
- No relative-time phrasing ("tip-off in 2 hours", "ended an hour ago").
  Absolute local time is sufficient and simpler.
- No multi-event handling (e.g., MLB doubleheaders). Existing behavior —
  return the first event matching the team — stands.
- No venue in the pre-game line. Users wanting venue should use
  `get_next_game`. Pre-game in the live-score path stays terse.
- No cross-day timezone handling. ESPN's scoreboard defines "today";
  trust it.

## State branching

`get_live_score` already extracts `status.type.state` from the scoreboard
event. The branching becomes:

| Existing scoreboard state | Existing response                            | New response                                                    |
| ------------------------- | -------------------------------------------- | --------------------------------------------------------------- |
| event not found           | `"do not have a live game right now"`        | unchanged                                                       |
| `state == "in"`           | live score line via `score_line`             | unchanged                                                       |
| `state == "post"`         | `"do not have a live game right now"`        | outcome narrative via new `final_outcome_line`                  |
| `state == "pre"`          | `"do not have a live game right now"`        | pre-game line via new `pre_game_line`                           |
| any other state           | `"do not have a live game right now"`        | unchanged                                                       |

The order in code: the existing `if state != "in"` early-return is replaced
by explicit `state == "post"` and `state == "pre"` branches. Anything else
falls through to the existing flat string.

## Output formats

All strings TTS-safe (no parens, slashes, ampersands, abbreviations,
score-style hyphens).

### Post-state — outcome narrative

From the queried team's perspective. The queried team's score is always
spoken first; this matches the framing of the natural question
("did *they* win?").

- **Win:** `"The Los Angeles Lakers beat the Boston Celtics 91 to 89."`
- **Loss:** `"The Los Angeles Lakers lost to the Boston Celtics 89 to 91."`
- **Tie / draw:** `"The Los Angeles Lakers and the Boston Celtics tied 1 to 1."`

The win/loss/tie verb is selected from the comparison
`team_score vs opp_score`. Ties exist primarily in soccer (EPL, MLS group
stage, UCL group stage, World Cup group stage). All other supported leagues
break ties before reaching the `post` state (NHL via OT/SO, NFL OT, NBA OT),
so in practice "tied" is rare outside soccer — but it is correct for those
sports too if a tie ever appears.

The verb is unconditionally lowercase "beat" / "lost to" / "tied". No
overtime suffix in this iteration.

### Pre-state — pre-game line

Names the opponent and the local-time tip-off. The queried team's name
appears first.

- **Away:** `"The Los Angeles Lakers don't have a live game yet. They play the Boston Celtics today at 7 30 PM."`
- **Home:** `"The Los Angeles Lakers don't have a live game yet. They host the Boston Celtics today at 7 30 PM."`

`"play"` vs `"host"` is selected by checking whether the queried team's
ESPN id matches the home competitor's id — same convention as
`get_next_game`. The date phrase comes from `fmt.date_phrase`; for an
event later today it returns `"today"`. The time phrase comes from
`fmt.time_phrase`. Venue is intentionally omitted to keep the live-score
response terse.

## New formatters

Two new pure functions in `sports_mcp/format.py`:

```python
def final_outcome_line(
    team_name: str,
    team_score: int,
    opp_name: str,
    opp_score: int,
) -> str:
    """Compose a TTS-safe final-score narrative from team_name's perspective."""

def pre_game_line(
    team_name: str,
    opp_name: str,
    when: datetime,
    is_home: bool,
) -> str:
    """Compose a TTS-safe pre-game line naming the opponent and tip-off time."""
```

Both follow the existing `format.py` conventions: no I/O, no business
logic, deterministic output, and outputs that pass `no_punctuation_artifacts`.

The "the" article in front of team names mirrors the existing
`unknown_team_message` and `final_outcome_line`'s natural reading flow. For
single-word team names (e.g., "Arsenal") the article still reads correctly:
`"The Arsenal don't have a live game yet."`. This is slightly stilted for
some clubs but consistent across leagues and easier to test than article
selection. Acceptable.

## Tool integration

In `sports_mcp/tools.py`, `get_live_score` adds two helpers' worth of
inline calls inside the existing function body. The state-branch reshape
is the only structural change; all other logic — alias resolution, league
lookup, ESPN fetch, error handling — is untouched.

After the existing line that determines `state`:

```python
state = (status.get("type") or {}).get("state")
```

replace the block:

```python
if state != "in":
    return f"The {info.name} do not have a live game right now."
```

with:

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
```

The existing live-game block (`state == "in"` happy path) follows
unchanged. `_parse_event_datetime` is already defined in `tools.py` from
`get_next_game`; reuse rather than redefine.

## Testing

### `tests/test_format.py`

Six new unit tests on the two formatters:

- `test_final_outcome_line_win` — `"The Lakers beat the Celtics 91 to 89."`
- `test_final_outcome_line_loss` — `"The Lakers lost to the Celtics 89 to 91."`
- `test_final_outcome_line_tie` — `"The Lakers and the Celtics tied 1 to 1."`
- `test_pre_game_line_away` — phrasing uses `"play"`, includes time and date phrase
- `test_pre_game_line_home` — phrasing uses `"host"`
- All six assert `no_punctuation_artifacts(s)` to lock TTS safety.

### `tests/test_tools.py`

Three new integration tests on `get_live_score`:

- `test_get_live_score_post_state_win` — Lakers in scoreboard with state
  `"post"` and a higher score. Asserts `"beat"` and final scores in output.
- `test_get_live_score_post_state_loss` — Lakers in scoreboard with state
  `"post"` and a lower score. Asserts `"lost to"`.
- `test_get_live_score_pre_state` — Lakers in scoreboard with state
  `"pre"` and a future date. Asserts `"don't have a live game yet"` and
  `"play"` (or `"host"`).

The existing `test_get_live_score_no_live_game` test continues to pass
without modification. Its payload uses `state == "pre"` but omits the
`date` field; the new pre-state branch parses the missing date as `None`
and falls through to the flat "do not have a live game right now" string.
That test now covers the legitimate edge case "pre-state event with
unparseable or missing date", which is worth keeping.

No tests need to be modified or removed; only new tests are added.

## Risks

- **Tool name precision drift.** `get_live_score` now answers questions
  beyond "live score". The natural-language responses make the intent
  clear, but a strict reading of the name is now stale. Mitigation:
  none — the alternative (renaming) breaks Home Assistant config and the
  current name still reads naturally for users.
- **`info.espn_id` string vs ESPN's int responses.** The existing code
  in `get_live_score` already compares via `str(team.get("id"))`. The new
  pre-state branch uses the same string-coerced compare. Consistent.
- **Event date present but unparseable.** `_parse_event_datetime` returns
  `None` on bad input; the pre-branch falls back to the flat "no live
  game" string. Same defensive pattern as elsewhere.
