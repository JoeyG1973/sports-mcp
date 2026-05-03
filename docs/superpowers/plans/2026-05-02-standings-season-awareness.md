# `get_standings` Season Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a phase prefix (offseason / postseason) and per-team playoff-qualification annotations to `get_standings`, while leaving regular-season output byte-for-byte unchanged.

**Architecture:** Two pure formatter additions — `standings_block` extended with an optional per-row `qualification` field, plus a new `season_phase_prefix` helper. In `tools.py`, two private detection helpers (`_detect_offseason`, `_detect_postseason`) compute the phase from the standings response itself; `_rows_from_standings_entries` passes through clinch information when the phase is non-regular; `get_standings` prepends the phase prefix.

**Tech Stack:** Python 3.13, `httpx` mocks via `pytest-asyncio`. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-05-02-standings-season-awareness-design.md](../specs/2026-05-02-standings-season-awareness-design.md)

---

## File Structure

Files modified by this plan:

- **`sports_mcp/format.py`** — extend `standings_block` to honor an optional per-row `qualification` key; add `season_phase_prefix` helper. ~25 lines added.
- **`sports_mcp/tools.py`** — add `_detect_offseason`, `_detect_postseason`; extend `_rows_from_standings_entries` to optionally emit `qualification`; modify `get_standings` to compute phase and prepend prefix. ~50 lines added/modified.
- **`tests/test_format.py`** — append 6 new unit tests across the formatter changes. ~80 lines.
- **`tests/test_tools.py`** — append 4 new integration tests for `get_standings` phase behavior. ~120 lines.

No files are created. No existing tests are modified — `test_get_standings_two_conferences` and `test_get_standings_single_table` continue to pass because their fixtures lack clinch data and lack a future `season.startDate`.

---

## Task 1: Extend `standings_block` with per-row qualification

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `tests/test_format.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_format.py`:

```python
def test_standings_block_with_qualified_annotation():
    rows = [
        {"name": "Boston Celtics", "wins": 52, "losses": 18, "qualification": "qualified"},
    ]
    s = standings_block("Eastern Conference", rows)
    assert s == (
        "Eastern Conference. "
        "Boston Celtics first at 52 wins and 18 losses, qualified for the playoffs."
    )
    assert no_punctuation_artifacts(s)


def test_standings_block_with_eliminated_annotation():
    rows = [
        {"name": "New Jersey Devils", "wins": 42, "losses": 37, "qualification": "eliminated"},
    ]
    s = standings_block("Eastern Conference", rows)
    assert s == (
        "Eastern Conference. "
        "New Jersey Devils first at 42 wins and 37 losses, did not qualify for the playoffs."
    )
    assert no_punctuation_artifacts(s)


def test_standings_block_no_qualification_unchanged():
    rows = [
        {"name": "Boston Celtics", "wins": 52, "losses": 18},
        {"name": "Milwaukee Bucks", "wins": 48, "losses": 22},
    ]
    s = standings_block("Eastern Conference", rows)
    assert s == (
        "Eastern Conference. "
        "Boston Celtics first at 52 wins and 18 losses. "
        "Milwaukee Bucks second at 48 wins and 22 losses."
    )
    assert no_punctuation_artifacts(s)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py::test_standings_block_with_qualified_annotation tests/test_format.py::test_standings_block_with_eliminated_annotation -v
```

Expected: both new annotation tests FAIL because the current `standings_block` ignores the `qualification` key. The third test (`test_standings_block_no_qualification_unchanged`) should already PASS — it documents the existing behavior.

- [ ] **Step 3: Modify `standings_block`**

In `sports_mcp/format.py`, find the existing `standings_block` function (around line 164):

```python
def standings_block(label: str, rows: list[dict]) -> str:
    """Render a standings table as TTS-safe prose.

    Each row is a dict with 'name', 'wins', 'losses'. Optional 'ties' key.
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
        parts.append(
            f"{row['name']} {rank} at {wins} {wins_word} and {losses} {losses_word}."
        )
    text = " ".join(parts)
    # Trim final period so we can re-add it cleanly with no double periods.
    return text.rstrip(".") + "."
```

Replace with:

```python
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
```

The change moves the trailing period from the f-string into a separate concatenation so the qualification phrase can be inserted before it. The regression test (`test_standings_block_no_qualification_unchanged`) confirms this preserves the existing format.

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: 35 prior + 3 new = 38 tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Extend standings_block with optional qualification annotation"
```

---

## Task 2: `season_phase_prefix` helper

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `tests/test_format.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_format.py`:

```python
from sports_mcp.format import season_phase_prefix


def test_season_phase_prefix_offseason():
    assert season_phase_prefix("NFL", "offseason") == (
        "The NFL is in the offseason. Last season. "
    )


def test_season_phase_prefix_postseason():
    assert season_phase_prefix("NHL", "postseason") == "The NHL is in the playoffs. "


def test_season_phase_prefix_regular_returns_empty():
    assert season_phase_prefix("NBA", "regular") == ""


def test_season_phase_prefix_unknown_returns_empty():
    assert season_phase_prefix("NBA", "wat") == ""
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py::test_season_phase_prefix_offseason -v
```

Expected: ImportError or AttributeError — `season_phase_prefix` is not yet defined.

- [ ] **Step 3: Implement `season_phase_prefix`**

Append to `sports_mcp/format.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: 38 prior + 4 new = 42 tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Add season_phase_prefix formatter for get_standings"
```

---

## Task 3: Phase detection helpers in `tools.py`

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

This task adds the two private detection functions but does not yet wire them into `get_standings`. Wiring happens in Task 4.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
from sports_mcp.tools import _detect_offseason, _detect_postseason


def test_detect_offseason_future_start_date():
    payload = {"season": {"startDate": "2099-08-06T07:00Z"}}
    assert _detect_offseason(payload) is True


def test_detect_offseason_past_start_date():
    payload = {"season": {"startDate": "2020-08-06T07:00Z"}}
    assert _detect_offseason(payload) is False


def test_detect_offseason_no_season_block():
    assert _detect_offseason({}) is False


def test_detect_offseason_unparseable_date():
    payload = {"season": {"startDate": "garbage"}}
    assert _detect_offseason(payload) is False


def test_detect_postseason_one_eliminated_team():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "clincher", "displayValue": "x"}]},
                        {"stats": [{"name": "clincher", "displayValue": "e"}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is True


def test_detect_postseason_no_eliminations():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "clincher", "displayValue": "x"}]},
                        {"stats": [{"name": "clincher", "displayValue": "y"}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is False


def test_detect_postseason_no_clinch_stat():
    payload = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {"stats": [{"name": "wins", "value": 25}]},
                    ]
                }
            }
        ]
    }
    assert _detect_postseason(payload) is False


def test_detect_postseason_empty_payload():
    assert _detect_postseason({}) is False
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py::test_detect_offseason_future_start_date -v
```

Expected: ImportError — neither helper is defined yet.

- [ ] **Step 3: Implement `_detect_offseason` and `_detect_postseason`**

In `sports_mcp/tools.py`, find this existing helper near line 230:

```python
def _stat_value(entry: dict, name: str) -> int:
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return int(stat.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0
```

Append the following two functions immediately after it:

```python
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
```

The first helper reuses the existing `_parse_event_datetime` already defined in `tools.py`. The `_dt` alias is already imported.

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 21 prior + 8 new = 29 tool tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Add _detect_offseason and _detect_postseason helpers"
```

---

## Task 4: Wire phase detection + clinch annotation into `get_standings`

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
async def test_get_standings_offseason_nfl():
    payload = {
        "name": "NFL Standings",
        "season": {"startDate": "2099-08-06T07:00Z"},
        "children": [
            {
                "name": "AFC East",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Buffalo Bills"},
                            "stats": [
                                {"name": "wins", "value": 12},
                                {"name": "losses", "value": 5},
                                {"name": "clincher", "displayValue": "y"},
                            ],
                        },
                        {
                            "team": {"displayName": "Miami Dolphins"},
                            "stats": [
                                {"name": "wins", "value": 9},
                                {"name": "losses", "value": 8},
                                {"name": "clincher", "displayValue": "e"},
                            ],
                        },
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NFL")
    finally:
        await c.aclose()
    assert s.startswith("The NFL is in the offseason. Last season. ")
    assert "Buffalo Bills first at 12 wins and 5 losses, qualified for the playoffs." in s
    assert "Miami Dolphins second at 9 wins and 8 losses, did not qualify for the playoffs." in s


async def test_get_standings_postseason_nhl():
    payload = {
        "name": "NHL Standings",
        "season": {"startDate": "2020-09-20T07:00Z"},
        "children": [
            {
                "name": "Eastern Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Carolina Hurricanes"},
                            "stats": [
                                {"name": "wins", "value": 53},
                                {"name": "losses", "value": 20},
                                {"name": "clincher", "displayValue": "z"},
                            ],
                        },
                        {
                            "team": {"displayName": "New Jersey Devils"},
                            "stats": [
                                {"name": "wins", "value": 42},
                                {"name": "losses", "value": 37},
                                {"name": "clincher", "displayValue": "e"},
                            ],
                        },
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NHL")
    finally:
        await c.aclose()
    assert s.startswith("The NHL is in the playoffs. ")
    assert "Carolina Hurricanes first at 53 wins and 20 losses, qualified for the playoffs." in s
    assert "New Jersey Devils second at 42 wins and 37 losses, did not qualify for the playoffs." in s


async def test_get_standings_regular_season_unchanged():
    payload = {
        "name": "NBA Standings",
        "season": {"startDate": "2020-10-01T07:00Z"},
        "children": [
            {
                "name": "Eastern Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Boston Celtics"},
                            "stats": [
                                {"name": "wins", "value": 52},
                                {"name": "losses", "value": 18},
                            ],
                        }
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    # No prefix, no per-team annotation. Output is exactly the pre-change format.
    assert s == "Eastern Conference. Boston Celtics first at 52 wins and 18 losses."


async def test_get_standings_postseason_no_clinch_data():
    """League past regular season but ESPN response lacks clincher stat per team.

    With no clinch data, _detect_postseason returns False. So the prefix
    is empty and no per-team annotations are added. This is the safe
    fallback path described in the spec.
    """
    payload = {
        "name": "Premier League",
        "season": {"startDate": "2020-08-01T07:00Z"},
        "children": [
            {
                "name": "Premier League",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Arsenal"},
                            "stats": [
                                {"name": "wins", "value": 25},
                                {"name": "losses", "value": 5},
                            ],
                        }
                    ]
                },
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "Premier League")
    finally:
        await c.aclose()
    assert s == "Premier League. Arsenal first at 25 wins and 5 losses."
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_standings_offseason_nfl -v
```

Expected: FAIL — current `get_standings` does not emit prefixes or qualification annotations.

- [ ] **Step 3: Modify `_rows_from_standings_entries` to optionally pass through qualification**

In `sports_mcp/tools.py`, find this existing function near line 240:

```python
def _rows_from_standings_entries(entries: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for e in entries:
        team_name = (e.get("team") or {}).get("displayName") or ""
        rows.append(
            {
                "name": team_name,
                "wins": _stat_value(e, "wins"),
                "losses": _stat_value(e, "losses"),
            }
        )
    return rows
```

Replace with:

```python
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
```

The default value of `annotate_qualification=False` keeps existing call sites (none other than `get_standings` exists, but the default protects future callers and matches the spec's "optional" framing).

- [ ] **Step 4: Modify `get_standings` to derive phase and prepend prefix**

In `sports_mcp/tools.py`, find the existing `get_standings` function:

```python
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

    blocks: list[str] = []
    for child in children:
        label = child.get("name") or info.name
        entries = ((child.get("standings") or {}).get("entries")) or []
        rows = _rows_from_standings_entries(entries)
        blocks.append(fmt.standings_block(label, rows))
    return " ".join(blocks)
```

Replace with:

```python
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
```

Three changes from the original:
1. Compute `phase` with the two new detection helpers (offseason takes precedence over postseason since "future startDate" is a stronger signal than "some teams eliminated"; in practice these don't overlap, but the order is defensive).
2. Pass `annotate_qualification` into `_rows_from_standings_entries` when phase is non-regular.
3. Prepend `season_phase_prefix(info.name, phase)` to the joined blocks. Returns `"" + blocks` for regular season — exactly the existing output.

- [ ] **Step 5: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 29 prior + 4 new = 33 tool tests pass. The existing
`test_get_standings_two_conferences` and `test_get_standings_single_table`
should continue to pass — their fixtures lack both clinch data and a
future `startDate`, so they route through the regular-season path.

If either existing test fails, inspect the test's payload — it should not have a `season` block (or the startDate is in the past) and no `clincher` stats. If it has either, the test was written before this enhancement and the new code is doing the right thing — but in that case the test needs updating, which is out of scope for this plan; report BLOCKED.

- [ ] **Step 6: Run full suite as a sanity check**

```bash
uv run pytest -q
```

Expected: 86 prior + 4 + 8 + 3 + 4 = 105 tests... wait, that's wrong. Let me recount. Prior: 86. New from Tasks 1, 2, 3, 4: 3 + 4 + 8 + 4 = 19. Total: 86 + 19 = 105.

```
105 passed
```

- [ ] **Step 7: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Surface offseason and postseason phases in get_standings"
```

---

## Task 5: Final integration check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: 105 tests pass.

- [ ] **Step 2: Live ESPN sanity probe**

```bash
uv run python -c "
import asyncio
from sports_mcp.espn import ESPNClient
from sports_mcp.tools import get_standings

async def main():
    c = ESPNClient()
    try:
        for league in ('NFL', 'NHL', 'NBA', 'MLB', 'Premier League'):
            s = await get_standings(c, league)
            print(f'=== {league} ===')
            print(s[:400])
            print()
    finally:
        await c.aclose()

asyncio.run(main())
"
```

Expected behavior at run time (May 2026):

- **NFL** — offseason: output starts with `"The NFL is in the offseason. Last season. "`. Top divisions show qualified/eliminated annotations from the most recent regular season.
- **NHL** — postseason (eliminations have happened): output starts with `"The NHL is in the playoffs. "`. Eastern and Western conferences each show 8 qualified teams and 8 eliminated teams.
- **NBA** — postseason: similar to NHL (the NBA finished its regular season in April 2026).
- **MLB** — regular season just started; very few or no clinch stats yet, no prefix.
- **Premier League** — mid-late season; no clinch instrumentation, no prefix.

If any output contains parens, slashes, ampersands, `vs.`, `@`, or score-style hyphens like `52-18` (instead of `52 wins and 18 losses`), that's a regression in the formatter or a leak in the data. The format tests should have caught this, but a human eyeball is the final check.

- [ ] **Step 3: Done**

No commit needed for Task 5.
