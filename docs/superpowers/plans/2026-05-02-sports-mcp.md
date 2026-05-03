# sports-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that exposes four ESPN-backed tools to Home Assistant over SSE on `0.0.0.0:8000`.

**Architecture:** A small Python package (`sports_mcp/`) with isolated, single-responsibility modules — TTL cache, alias resolution, ESPN HTTP client, TTS-safe formatters, four tool implementations, and an MCP server entry point. Strict TDD with fixture-backed tests; no live HTTP in CI.

**Tech Stack:** Python 3.13, `mcp >= 1.27.0`, `httpx >= 0.28.1`, `pytest`, `pytest-asyncio`, `uv` for dependency management.

**Spec:** [docs/superpowers/specs/2026-05-02-sports-mcp-design.md](../specs/2026-05-02-sports-mcp-design.md)

---

## File Structure

Files created or modified by this plan:

- **`pyproject.toml`** (modify): add dev deps, console script entry, pytest config.
- **`main.py`** (delete): replaced by package entry point.
- **`sports_mcp/__init__.py`** (create): package marker, version.
- **`sports_mcp/__main__.py`** (create): `python -m sports_mcp` entry, calls `server.main()`.
- **`sports_mcp/cache.py`** (create): `TTLCache` class. Pure logic, ~30 lines.
- **`sports_mcp/aliases.py`** (create): types, league registry, resolvers. ~150 lines.
- **`sports_mcp/teams_data.py`** (create, machine-generated): the team registry, harvested from ESPN. ~250 entries.
- **`sports_mcp/format.py`** (create): TTS-safe formatters and number-to-words helpers. ~200 lines.
- **`sports_mcp/espn.py`** (create): `ESPNClient` with two-base-URL routing and cache wiring. ~120 lines.
- **`sports_mcp/tools.py`** (create): four tool functions, orchestration only. ~150 lines.
- **`sports_mcp/server.py`** (create): MCP server, tool registration, SSE entry. ~50 lines.
- **`scripts/harvest_teams.py`** (create): one-shot harvester for `teams_data.py`. ~80 lines.
- **`scripts/smoke.py`** (create): manual integration check. ~50 lines.
- **`tests/conftest.py`** (create): pytest config + shared fixtures.
- **`tests/fixtures/*.json`** (create): captured ESPN responses for tests.
- **`tests/test_cache.py`**, **`test_aliases.py`**, **`test_format.py`**, **`test_espn.py`**, **`test_tools.py`** (create).
- **`README.md`** (modify): replace empty file with run + Home Assistant config docs.

---

## Task 1: Project setup

**Files:**
- Modify: `pyproject.toml`
- Delete: `main.py`
- Create: `sports_mcp/__init__.py`, `sports_mcp/__main__.py` (stub)
- Create: `tests/__init__.py`, `tests/conftest.py`
- Create: `scripts/` directory marker
- Modify: `.gitignore`

- [ ] **Step 1: Update `pyproject.toml`**

Replace the contents of `pyproject.toml` with:

```toml
[project]
name = "sports-mcp"
version = "0.1.0"
description = "MCP server wrapping ESPN's public API for Home Assistant"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "httpx>=0.28.1",
    "mcp>=1.27.0",
]

[project.scripts]
sports-mcp = "sports_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["sports_mcp"]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package skeleton**

```bash
mkdir -p sports_mcp tests/fixtures scripts
```

Create `sports_mcp/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `sports_mcp/__main__.py`:

```python
from sports_mcp.server import main

if __name__ == "__main__":
    main()
```

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures and configuration."""
```

Create `scripts/.gitkeep` (empty file).

- [ ] **Step 3: Update `.gitignore`**

Append to existing `.gitignore`:

```
# Editor
.idea/
.vscode/

# pytest
.pytest_cache/

# Coverage
.coverage
htmlcov/
```

- [ ] **Step 4: Delete `main.py`**

```bash
rm main.py
```

- [ ] **Step 5: Sync deps and verify**

```bash
uv sync --group dev
```

Expected: `Resolved N packages` then `Installed N packages`. No errors.

```bash
uv run pytest -q
```

Expected: `no tests ran in X.XXs` (no tests yet, but pytest discovers correctly).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .python-version README.md \
        sports_mcp/ tests/ scripts/
git rm main.py
git commit -m "Initialize package layout and pytest scaffolding"
```

---

## Task 2: TTLCache

**Files:**
- Create: `sports_mcp/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache.py`:

```python
from sports_mcp.cache import TTLCache


def test_set_and_get_round_trip():
    cache = TTLCache(clock=lambda: 0.0)
    cache.set("k", "v", ttl_seconds=10)
    assert cache.get("k") == "v"


def test_get_missing_returns_none():
    cache = TTLCache(clock=lambda: 0.0)
    assert cache.get("missing") is None


def test_value_expires_after_ttl():
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0])
    cache.set("k", "v", ttl_seconds=10)
    now[0] = 9.999
    assert cache.get("k") == "v"
    now[0] = 10.0
    assert cache.get("k") is None


def test_keys_isolated():
    cache = TTLCache(clock=lambda: 0.0)
    cache.set("a", 1, ttl_seconds=10)
    cache.set("b", 2, ttl_seconds=10)
    assert cache.get("a") == 1
    assert cache.get("b") == 2


def test_set_overwrites_existing():
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0])
    cache.set("k", "v1", ttl_seconds=10)
    now[0] = 5.0
    cache.set("k", "v2", ttl_seconds=10)
    now[0] = 14.999
    assert cache.get("k") == "v2"
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'sports_mcp.cache'` or similar collection failure.

- [ ] **Step 3: Implement `TTLCache`**

Create `sports_mcp/cache.py`:

```python
"""Tiny in-memory TTL cache for HTTP responses."""
import time
from typing import Any, Callable


class TTLCache:
    """Process-local cache with per-entry TTL and lazy expiry on read."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._clock = clock

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._store[key] = (value, self._clock() + ttl_seconds)
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/cache.py tests/test_cache.py
git commit -m "Add TTLCache with injectable clock for testability"
```

---

## Task 3: Alias types and league registry

**Files:**
- Create: `sports_mcp/aliases.py`
- Create: `tests/test_aliases.py`

- [ ] **Step 1: Write failing tests for league resolution**

Create `tests/test_aliases.py`:

```python
from sports_mcp.aliases import (
    LEAGUE_REGISTRY,
    LeagueInfo,
    resolve_league,
)


def test_league_registry_has_eight_leagues():
    assert len(LEAGUE_REGISTRY) == 8


def test_league_registry_slugs_are_unique():
    slugs = [li.slug for li in LEAGUE_REGISTRY]
    assert len(slugs) == len(set(slugs))


def test_resolve_league_by_short_name():
    li = resolve_league("NBA")
    assert li is not None
    assert li.slug == "basketball/nba"


def test_resolve_league_case_insensitive():
    assert resolve_league("nba") == resolve_league("NBA") == resolve_league("Nba")


def test_resolve_league_by_long_alias():
    li = resolve_league("Premier League")
    assert li is not None
    assert li.slug == "soccer/eng.1"


def test_resolve_league_alternate_alias():
    assert resolve_league("EPL").slug == "soccer/eng.1"
    assert resolve_league("English Premier League").slug == "soccer/eng.1"


def test_resolve_league_unknown_returns_none():
    assert resolve_league("Quidditch") is None


def test_resolve_world_cup():
    assert resolve_league("World Cup").slug == "soccer/fifa.world"


def test_resolve_champions_league():
    li = resolve_league("Champions League")
    assert li is not None
    assert li.slug == "soccer/uefa.champions"
    assert resolve_league("UCL") == li
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_aliases.py -v
```

Expected: import error for `sports_mcp.aliases`.

- [ ] **Step 3: Implement types and league registry**

Create `sports_mcp/aliases.py`:

```python
"""League and team aliases plus resolver functions.

The TEAM_REGISTRY is generated by scripts/harvest_teams.py and lives in
teams_data.py. This module owns the data structures, the LEAGUE_REGISTRY,
and the resolve_* functions.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueInfo:
    """One supported league."""

    name: str  # display name, e.g. "NBA"
    sport: str  # ESPN sport segment, e.g. "basketball"
    slug: str  # full sport/league slug, e.g. "basketball/nba"
    aliases: tuple[str, ...]  # lowercase alias keys


@dataclass(frozen=True)
class TeamInfo:
    """One team within a league."""

    name: str  # display name, e.g. "Los Angeles Lakers"
    league_slug: str  # parent league slug
    espn_id: str  # ESPN team id (string for safety; ESPN uses both)
    abbreviation: str  # short code, e.g. "LAL"
    aliases: tuple[str, ...]  # lowercase alias keys


LEAGUE_REGISTRY: list[LeagueInfo] = [
    LeagueInfo(
        name="NFL",
        sport="football",
        slug="football/nfl",
        aliases=("nfl", "national football league"),
    ),
    LeagueInfo(
        name="NBA",
        sport="basketball",
        slug="basketball/nba",
        aliases=("nba", "national basketball association"),
    ),
    LeagueInfo(
        name="MLB",
        sport="baseball",
        slug="baseball/mlb",
        aliases=("mlb", "major league baseball"),
    ),
    LeagueInfo(
        name="NHL",
        sport="hockey",
        slug="hockey/nhl",
        aliases=("nhl", "national hockey league"),
    ),
    LeagueInfo(
        name="Premier League",
        sport="soccer",
        slug="soccer/eng.1",
        aliases=(
            "epl",
            "premier league",
            "english premier league",
            "the premier league",
        ),
    ),
    LeagueInfo(
        name="MLS",
        sport="soccer",
        slug="soccer/usa.1",
        aliases=("mls", "major league soccer"),
    ),
    LeagueInfo(
        name="World Cup",
        sport="soccer",
        slug="soccer/fifa.world",
        aliases=("world cup", "fifa world cup", "the world cup"),
    ),
    LeagueInfo(
        name="Champions League",
        sport="soccer",
        slug="soccer/uefa.champions",
        aliases=(
            "ucl",
            "champions league",
            "uefa champions league",
            "the champions league",
        ),
    ),
]


def _build_league_index() -> dict[str, LeagueInfo]:
    index: dict[str, LeagueInfo] = {}
    for li in LEAGUE_REGISTRY:
        for alias in li.aliases:
            index[alias] = li
        index[li.name.lower()] = li
    return index


LEAGUES: dict[str, LeagueInfo] = _build_league_index()


def resolve_league(text: str) -> LeagueInfo | None:
    """Resolve a free-text league name to a LeagueInfo, or None."""
    return LEAGUES.get(text.strip().lower())
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_aliases.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/aliases.py tests/test_aliases.py
git commit -m "Add league registry with eight leagues and resolve_league"
```

---

## Task 4: Harvest team data from ESPN

**Files:**
- Create: `scripts/harvest_teams.py`
- Create: `sports_mcp/teams_data.py` (generated)

- [ ] **Step 1: Write the harvester**

Create `scripts/harvest_teams.py`:

```python
"""Harvest team data from ESPN's teams endpoint into sports_mcp/teams_data.py.

Run once during initial setup, and re-run when leagues change rosters
(e.g., expansion teams). The output is a Python source file that is committed.

Usage:
    uv run python scripts/harvest_teams.py > sports_mcp/teams_data.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from sports_mcp.aliases import LEAGUE_REGISTRY


async def fetch_teams(client: httpx.AsyncClient, slug: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams"
    print(f"Fetching {url}", file=sys.stderr)
    r = await client.get(url, timeout=15.0)
    r.raise_for_status()
    data = r.json()
    teams: list[dict] = []
    for sport in data.get("sports", []):
        for league in sport.get("leagues", []):
            for entry in league.get("teams", []):
                team = entry.get("team")
                if team:
                    teams.append(team)
    return teams


def build_aliases(team: dict) -> tuple[str, ...]:
    candidates: set[str] = set()
    for key in ("displayName", "name", "shortDisplayName", "nickname", "abbreviation"):
        v = team.get(key)
        if v:
            candidates.add(str(v).strip().lower())
    return tuple(sorted(candidates))


def emit_team(slug: str, team: dict) -> str:
    name = team["displayName"]
    abbreviation = team.get("abbreviation") or ""
    espn_id = str(team["id"])
    aliases = build_aliases(team)
    aliases_repr = ", ".join(repr(a) for a in aliases)
    return (
        "    TeamInfo(\n"
        f"        name={name!r},\n"
        f"        league_slug={slug!r},\n"
        f"        espn_id={espn_id!r},\n"
        f"        abbreviation={abbreviation!r},\n"
        f"        aliases=({aliases_repr},),\n"
        "    ),"
    )


async def main() -> None:
    out_lines = [
        '"""Auto-generated team registry. Edit scripts/harvest_teams.py and re-run."""',
        "from sports_mcp.aliases import TeamInfo",
        "",
        "TEAM_REGISTRY: list[TeamInfo] = [",
    ]
    async with httpx.AsyncClient() as client:
        for li in LEAGUE_REGISTRY:
            try:
                teams = await fetch_teams(client, li.slug)
            except httpx.HTTPError as e:
                print(f"WARN: failed to fetch {li.slug}: {e}", file=sys.stderr)
                continue
            print(f"  -> {len(teams)} teams in {li.slug}", file=sys.stderr)
            for team in teams:
                out_lines.append(emit_team(li.slug, team))
    out_lines.append("]")
    print("\n".join(out_lines))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the harvester**

```bash
uv run python scripts/harvest_teams.py > sports_mcp/teams_data.py
```

Expected stderr output (approximate counts):

```
Fetching https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
  -> 32 teams in football/nfl
Fetching https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams
  -> 30 teams in basketball/nba
Fetching https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams
  -> 30 teams in baseball/mlb
Fetching https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams
  -> 32 teams in hockey/nhl
Fetching https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams
  -> 20 teams in soccer/eng.1
Fetching https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/teams
  -> 29 teams in soccer/usa.1
Fetching https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams
  -> N teams in soccer/fifa.world          (variable; may be 0 outside tournaments)
Fetching https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/teams
  -> N teams in soccer/uefa.champions
```

If any league returns 0 teams, that's acceptable for World Cup or Champions League outside their seasons; do not abort.

- [ ] **Step 3: Sanity-check the generated file**

```bash
uv run python -c "from sports_mcp.teams_data import TEAM_REGISTRY; print(len(TEAM_REGISTRY))"
```

Expected: a number greater than 140 (sum of NFL 32 + NBA 30 + MLB 30 + NHL 32 + EPL 20 = 144 minimum; soccer competitions add more when active).

```bash
uv run python -c "
from sports_mcp.teams_data import TEAM_REGISTRY
from collections import Counter
c = Counter(t.league_slug for t in TEAM_REGISTRY)
for slug, n in sorted(c.items()):
    print(f'{slug}: {n}')
"
```

Expected: per-league counts roughly matching the fetch output.

- [ ] **Step 4: Commit**

```bash
git add scripts/harvest_teams.py sports_mcp/teams_data.py
git commit -m "Harvest team registry from ESPN's teams endpoint"
```

---

## Task 5: resolve_team

**Files:**
- Modify: `sports_mcp/aliases.py`
- Modify: `tests/test_aliases.py`

- [ ] **Step 1: Add failing tests for resolve_team**

Append to `tests/test_aliases.py`:

```python
from sports_mcp.aliases import (
    TeamMatch,
    TeamMatchAmbiguous,
    TeamMatchNone,
    TeamMatchOne,
    resolve_team,
)


def test_resolve_team_single_match():
    m = resolve_team("Lakers")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"
    assert m.team.league_slug == "basketball/nba"


def test_resolve_team_case_insensitive():
    assert resolve_team("LAKERS").__class__ is TeamMatchOne
    assert resolve_team("lakers").__class__ is TeamMatchOne


def test_resolve_team_by_full_name():
    m = resolve_team("Los Angeles Lakers")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"


def test_resolve_team_by_abbreviation():
    m = resolve_team("LAL")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"


def test_resolve_team_ambiguous_giants():
    m = resolve_team("Giants")
    assert isinstance(m, TeamMatchAmbiguous)
    slugs = {t.league_slug for t in m.teams}
    assert "football/nfl" in slugs
    assert "baseball/mlb" in slugs


def test_resolve_team_prefer_league_breaks_tie():
    m = resolve_team("Giants", prefer_league="basketball/nba")
    # Giants is not in NBA, so still ambiguous, falls back
    assert isinstance(m, TeamMatchAmbiguous)
    m2 = resolve_team("Giants", prefer_league="football/nfl")
    assert isinstance(m2, TeamMatchOne)
    assert m2.team.league_slug == "football/nfl"


def test_resolve_team_unknown_with_suggestions():
    m = resolve_team("Lkaers")
    assert isinstance(m, TeamMatchNone)
    # Suggestions should include something close to Lakers
    suggestion_text = " ".join(m.suggestions).lower()
    assert "laker" in suggestion_text


def test_resolve_team_unknown_no_close_match():
    m = resolve_team("zzzzzzzzzzzz")
    assert isinstance(m, TeamMatchNone)
    assert m.suggestions == []
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_aliases.py -v
```

Expected: import errors for `TeamMatch*` and `resolve_team`.

- [ ] **Step 3: Implement TeamMatch types and resolve_team**

Append to `sports_mcp/aliases.py`:

```python
from sports_mcp.teams_data import TEAM_REGISTRY


@dataclass(frozen=True)
class TeamMatchOne:
    """Exactly one team matched."""

    team: TeamInfo


@dataclass(frozen=True)
class TeamMatchAmbiguous:
    """Multiple teams matched the alias."""

    teams: tuple[TeamInfo, ...]


@dataclass(frozen=True)
class TeamMatchNone:
    """No team matched. May include fuzzy suggestions."""

    suggestions: list[str]


TeamMatch = TeamMatchOne | TeamMatchAmbiguous | TeamMatchNone


def _build_team_index() -> dict[str, list[TeamInfo]]:
    index: dict[str, list[TeamInfo]] = {}
    for t in TEAM_REGISTRY:
        for alias in t.aliases:
            index.setdefault(alias, []).append(t)
    return index


TEAMS: dict[str, list[TeamInfo]] = _build_team_index()


def _all_alias_strings() -> list[str]:
    return list(TEAMS.keys())


def resolve_team(
    text: str,
    prefer_league: str | None = None,
) -> TeamMatch:
    """Resolve a free-text team name to a TeamMatch.

    If multiple teams share the alias and prefer_league disambiguates,
    return the unique match in that league. Otherwise return ambiguous.

    For unknown aliases, return TeamMatchNone with up to three close
    suggestions via difflib.
    """
    key = text.strip().lower()
    matches = TEAMS.get(key, [])

    if prefer_league is not None and matches:
        in_league = [t for t in matches if t.league_slug == prefer_league]
        if len(in_league) == 1:
            return TeamMatchOne(in_league[0])

    if len(matches) == 1:
        return TeamMatchOne(matches[0])
    if len(matches) > 1:
        return TeamMatchAmbiguous(tuple(matches))

    suggestions = difflib.get_close_matches(key, _all_alias_strings(), n=3, cutoff=0.6)
    return TeamMatchNone(list(suggestions))
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_aliases.py -v
```

Expected: all tests pass (the original 9 plus the 8 new ones).

If `test_resolve_team_ambiguous_giants` fails because the harvested aliases don't share the literal string "giants" across both leagues, inspect the harvested aliases:

```bash
uv run python -c "
from sports_mcp.aliases import TEAMS
print(TEAMS.get('giants'))
"
```

If "giants" is missing from one league, augment the harvest by editing `sports_mcp/teams_data.py` and adding `'giants'` to the aliases tuple of both NYG and SFG, then re-run tests.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/aliases.py tests/test_aliases.py
# Include any manual edits to teams_data.py from the previous step:
git add sports_mcp/teams_data.py 2>/dev/null || true
git commit -m "Add resolve_team with ambiguity and fuzzy fallback"
```

---

## Task 6: Format helpers — numbers, dates, score lines

**Files:**
- Create: `sports_mcp/format.py`
- Create: `tests/test_format.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_format.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py -v
```

Expected: import errors.

- [ ] **Step 3: Implement format helpers**

Create `sports_mcp/format.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Add TTS-safe formatters for clocks, periods, scores, and dates"
```

---

## Task 7: Format helpers — standings, league status, error messages

**Files:**
- Modify: `sports_mcp/format.py`
- Modify: `tests/test_format.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_format.py`:

```python
from sports_mcp.format import (
    ambiguity_message,
    league_status_block,
    standings_block,
    unknown_league_message,
    unknown_team_message,
)


def test_standings_block_simple_table():
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


def test_standings_block_empty():
    s = standings_block("Eastern Conference", [])
    assert s == "Eastern Conference standings are not available."


def test_league_status_block_in_season_with_games():
    s = league_status_block(
        "NBA",
        season_phrase="regular season, week 12",
        events_phrase="Lakers at Celtics, fourth quarter. Heat at Knicks, scheduled 7 30 PM.",
    )
    assert s == (
        "The NBA is in the regular season, week 12. "
        "Lakers at Celtics, fourth quarter. Heat at Knicks, scheduled 7 30 PM."
    )
    assert no_punctuation_artifacts(s)


def test_league_status_block_no_events():
    s = league_status_block(
        "NBA",
        season_phrase="regular season, week 12",
        events_phrase="",
    )
    assert s == "The NBA is in the regular season, week 12. No games today."


def test_league_status_block_offseason():
    s = league_status_block(
        "NFL",
        season_phrase="offseason",
        events_phrase="",
    )
    assert s == "The NFL is in the offseason. No games today."


def test_ambiguity_message():
    s = ambiguity_message(
        "Giants",
        ["the NFL Giants", "the MLB Giants"],
    )
    assert s == "Giants is ambiguous. Did you mean the NFL Giants or the MLB Giants?"
    assert no_punctuation_artifacts(s)


def test_ambiguity_message_three_options():
    s = ambiguity_message(
        "Cardinals",
        ["the NFL Cardinals", "the MLB Cardinals", "the college Cardinals"],
    )
    assert s == (
        "Cardinals is ambiguous. "
        "Did you mean the NFL Cardinals, the MLB Cardinals, or the college Cardinals?"
    )


def test_unknown_team_message_with_suggestions():
    s = unknown_team_message("Lkaers", ["lakers", "clippers"])
    assert s == "I don't recognize Lkaers. Did you mean lakers or clippers?"


def test_unknown_team_message_no_suggestions():
    s = unknown_team_message("zzzzz", [])
    assert s == "I don't recognize zzzzz."


def test_unknown_league_message():
    s = unknown_league_message("KHL", ["nhl"])
    assert s == "I don't recognize KHL. Did you mean nhl?"
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_format.py -v
```

Expected: 8 new failures (import errors).

- [ ] **Step 3: Implement remaining formatters**

Append to `sports_mcp/format.py`:

```python
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


def league_status_block(
    league_name: str,
    season_phrase: str,
    events_phrase: str,
) -> str:
    """Combine season context and today's slate into one TTS-safe paragraph."""
    head = f"The {league_name} is in the {season_phrase}."
    body = events_phrase.strip() if events_phrase else "No games today."
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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_format.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/format.py tests/test_format.py
git commit -m "Add standings, league status, and error message formatters"
```

---

## Task 8: ESPNClient — URL routing skeleton

**Files:**
- Create: `sports_mcp/espn.py`
- Create: `tests/test_espn.py`
- Create: `tests/fixtures/nba_scoreboard.json`

- [ ] **Step 1: Capture a real NBA scoreboard fixture**

```bash
curl -s "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard" \
  > tests/fixtures/nba_scoreboard.json
```

Verify it's a non-trivial JSON file:

```bash
python3 -c "import json; print(len(json.load(open('tests/fixtures/nba_scoreboard.json'))['events']), 'events')"
```

Expected: a number (could be 0 if a quiet day, but the file is well-formed JSON with `events` key).

If `events` is missing or the file is tiny, retry the curl during a more active sports day or use a date param: `?dates=20250115`.

- [ ] **Step 2: Write failing tests for URL routing**

Create `tests/test_espn.py`:

```python
import json
from pathlib import Path

import httpx
import pytest

from sports_mcp.espn import ESPNClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def captured_urls():
    return []


@pytest.fixture
def mock_transport(captured_urls):
    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        if "/scoreboard" in request.url.path and "basketball/nba" in request.url.path:
            return httpx.Response(200, json=load("nba_scoreboard.json"))
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
async def client(mock_transport):
    c = ESPNClient(transport=mock_transport)
    yield c
    await c.aclose()


async def test_scoreboard_uses_site_v2_path(client, captured_urls):
    await client.scoreboard("basketball/nba")
    assert any(
        "site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard" in u
        for u in captured_urls
    )


async def test_standings_uses_v2_path_without_site():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, json={"name": "stub", "children": []})

    transport = httpx.MockTransport(handler)
    c = ESPNClient(transport=transport)
    try:
        await c.standings("basketball/nba")
    finally:
        await c.aclose()
    assert len(captured) == 1
    assert "site.api.espn.com/apis/v2/sports/basketball/nba/standings" in captured[0]
    assert "/apis/site/v2/" not in captured[0]
```

- [ ] **Step 3: Run tests and verify failure**

```bash
uv run pytest tests/test_espn.py -v
```

Expected: import error for `sports_mcp.espn`.

- [ ] **Step 4: Implement ESPNClient skeleton**

Create `sports_mcp/espn.py`:

```python
"""Async ESPN HTTP client with TTL caching and two-base-URL routing.

ESPN exposes scoreboard/teams/schedule under /apis/site/v2/ and standings
under /apis/v2/ (the 'site' segment is dropped). Hitting the wrong base
returns either 404s or stub responses. This client routes correctly per
endpoint type.
"""
from __future__ import annotations

from typing import Any

import httpx

from sports_mcp.cache import TTLCache

_BASE_SITE_V2 = "https://site.api.espn.com/apis/site/v2"
_BASE_V2 = "https://site.api.espn.com/apis/v2"

DEFAULT_TIMEOUT = 8.0


class ESPNClient:
    """Async wrapper around ESPN's hidden HTTP API."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        cache: TTLCache | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._cache = cache or TTLCache()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, ttl_seconds: float) -> dict[str, Any]:
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        response = await self._client.get(url)
        response.raise_for_status()
        data = response.json()
        self._cache.set(url, data, ttl_seconds)
        return data

    async def scoreboard(self, league_slug: str, dates: str | None = None) -> dict[str, Any]:
        url = f"{_BASE_SITE_V2}/sports/{league_slug}/scoreboard"
        if dates:
            url = f"{url}?dates={dates}"
        return await self._get_json(url, ttl_seconds=15.0)

    async def team_schedule(self, league_slug: str, team_id: str) -> dict[str, Any]:
        url = f"{_BASE_SITE_V2}/sports/{league_slug}/teams/{team_id}/schedule"
        return await self._get_json(url, ttl_seconds=300.0)

    async def standings(self, league_slug: str) -> dict[str, Any]:
        url = f"{_BASE_V2}/sports/{league_slug}/standings"
        return await self._get_json(url, ttl_seconds=300.0)
```

- [ ] **Step 5: Run tests and verify pass**

```bash
uv run pytest tests/test_espn.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add sports_mcp/espn.py tests/test_espn.py tests/fixtures/nba_scoreboard.json
git commit -m "Add ESPNClient with two-base-URL routing and cache wiring"
```

---

## Task 9: ESPNClient — caching, error paths, schedule fixture

**Files:**
- Modify: `tests/test_espn.py`
- Create: `tests/fixtures/nba_team_schedule.json`
- Create: `tests/fixtures/nba_standings.json`

- [ ] **Step 1: Capture additional fixtures**

```bash
# Lakers team id is 13. If that has changed, look it up first:
curl -s "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/13/schedule" \
  > tests/fixtures/nba_team_schedule.json
curl -s "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings" \
  > tests/fixtures/nba_standings.json
```

Sanity-check both files contain valid JSON:

```bash
python3 -c "import json; d=json.load(open('tests/fixtures/nba_team_schedule.json')); print('events:', len(d.get('events', [])))"
python3 -c "import json; d=json.load(open('tests/fixtures/nba_standings.json')); print('children:', len(d.get('children', [])))"
```

- [ ] **Step 2: Add tests for caching and HTTP errors**

Append to `tests/test_espn.py`:

```python
async def test_cache_hit_skips_second_request(captured_urls, mock_transport):
    c = ESPNClient(transport=mock_transport)
    try:
        await c.scoreboard("basketball/nba")
        await c.scoreboard("basketball/nba")
    finally:
        await c.aclose()
    assert len(captured_urls) == 1


async def test_team_schedule_fetches_and_returns():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/teams/13/schedule" in request.url.path:
            return httpx.Response(200, json=load("nba_team_schedule.json"))
        return httpx.Response(404, json={})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        data = await c.team_schedule("basketball/nba", "13")
    finally:
        await c.aclose()
    assert "events" in data or "team" in data


async def test_standings_returns_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("nba_standings.json"))

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        data = await c.standings("basketball/nba")
    finally:
        await c.aclose()
    assert "children" in data or "name" in data


async def test_http_5xx_raises_status_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await c.scoreboard("basketball/nba")
    finally:
        await c.aclose()


async def test_dates_param_appended():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, json={"events": [], "leagues": []})

    c = ESPNClient(transport=httpx.MockTransport(handler))
    try:
        await c.scoreboard("basketball/nba", dates="20260508")
    finally:
        await c.aclose()
    assert "dates=20260508" in captured[0]
```

- [ ] **Step 3: Run tests and verify pass**

```bash
uv run pytest tests/test_espn.py -v
```

Expected: 5 new tests pass (7 total in file).

- [ ] **Step 4: Commit**

```bash
git add tests/test_espn.py tests/fixtures/nba_team_schedule.json tests/fixtures/nba_standings.json
git commit -m "Test ESPNClient cache hits, team schedule, standings, errors"
```

---

## Task 10: tools.get_live_score

**Files:**
- Create: `sports_mcp/tools.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tools.py`:

```python
"""Tests for the four MCP tool functions.

Each tool is tested with: a happy path, an empty-result path, and an
ESPN-unreachable path. ESPN responses are mocked; alias resolution is real.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sports_mcp.espn import ESPNClient
from sports_mcp.tools import get_live_score

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def make_client(handler) -> ESPNClient:
    return ESPNClient(transport=httpx.MockTransport(handler))


async def test_get_live_score_unknown_team():
    c = make_client(lambda r: httpx.Response(200, json={"events": []}))
    try:
        s = await get_live_score(c, "Quidditch United")
    finally:
        await c.aclose()
    assert "I don't recognize" in s
    assert "Quidditch United" in s


async def test_get_live_score_ambiguous_team():
    # Build a synthetic scoreboard that won't be reached.
    c = make_client(lambda r: httpx.Response(200, json={"events": []}))
    try:
        s = await get_live_score(c, "Giants")
    finally:
        await c.aclose()
    assert s.startswith("Giants is ambiguous.")


async def test_get_live_score_no_live_game(monkeypatch):
    # A scoreboard with the Lakers in a 'pre' state (scheduled, not started).
    payload = {
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "score": "0", "homeAway": "home"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "score": "0", "homeAway": "away"},
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
    assert "Lakers" in s
    assert "do not have a live game" in s or "don't have a live game" in s


async def test_get_live_score_live_game():
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
                        "status": {"type": {"state": "in", "description": "In Progress"}, "period": 4, "displayClock": "2:34"},
                    }
                ],
            }
        ],
        "leagues": [{"slug": "nba"}],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert "Los Angeles Lakers 89" in s
    assert "Boston Celtics 91" in s
    assert "fourth quarter" in s
    assert "2 minutes 34 seconds" in s


async def test_get_live_score_espn_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_live_score(c, "Lakers")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: import errors.

- [ ] **Step 3: Implement `get_live_score`**

Create `sports_mcp/tools.py`:

```python
"""The four MCP tool functions.

Each tool returns a TTS-safe string and never raises. HTTP and slug-map
errors are translated into prose and logged.
"""
from __future__ import annotations

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

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Implement get_live_score with full alias and error handling"
```

---

## Task 11: tools.get_next_game

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
from sports_mcp.tools import get_next_game


async def test_get_next_game_unknown_team():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_next_game(c, "Quidditch United")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_next_game_no_upcoming():
    payload = {"events": []}
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "do not have a scheduled game" in s


async def test_get_next_game_with_upcoming():
    # ESPN returns ISO 8601 UTC. Pick a date several months out so the
    # weekday/calendar phrasing doesn't depend on test-run date.
    payload = {
        "events": [
            {
                "id": "1",
                "date": "2099-12-25T01:00Z",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"id": "13", "displayName": "Los Angeles Lakers"}, "homeAway": "away"},
                            {"team": {"id": "2", "displayName": "Boston Celtics"}, "homeAway": "home"},
                        ],
                        "venue": {"fullName": "TD Garden"},
                        "status": {"type": {"state": "pre"}},
                    }
                ],
            }
        ]
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "Los Angeles Lakers" in s
    assert "Boston Celtics" in s
    assert "TD Garden" in s


async def test_get_next_game_espn_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_next_game(c, "Lakers")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 4 new failures.

- [ ] **Step 3: Implement `get_next_game`**

Append to `sports_mcp/tools.py`:

```python
import datetime as _dt


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
```

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Implement get_next_game with date phrasing and venue"
```

---

## Task 12: tools.get_standings

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
from sports_mcp.tools import get_standings


async def test_get_standings_unknown_league():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_standings(c, "Quidditch")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_standings_two_conferences():
    payload = {
        "name": "NBA Standings",
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
                        },
                        {
                            "team": {"displayName": "Milwaukee Bucks"},
                            "stats": [
                                {"name": "wins", "value": 48},
                                {"name": "losses", "value": 22},
                            ],
                        },
                    ]
                },
            },
            {
                "name": "Western Conference",
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Denver Nuggets"},
                            "stats": [
                                {"name": "wins", "value": 50},
                                {"name": "losses", "value": 20},
                            ],
                        }
                    ]
                },
            },
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    assert "Eastern Conference" in s
    assert "Western Conference" in s
    assert "Boston Celtics first at 52 wins and 18 losses" in s


async def test_get_standings_single_table():
    payload = {
        "name": "Premier League",
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
    assert "Arsenal first at 25 wins and 5 losses" in s


async def test_get_standings_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_standings(c, "NBA")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py -v
```

- [ ] **Step 3: Implement `get_standings`**

Append to `sports_mcp/tools.py`:

```python
def _stat_value(entry: dict, name: str) -> int:
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return int(stat.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


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


def _league_alias_strings() -> list[str]:
    out: list[str] = []
    for li in LEAGUE_REGISTRY:
        out.extend(li.aliases)
        out.append(li.name.lower())
    return out


async def get_standings(client: ESPNClient, league: str) -> str:
    info = resolve_league(league)
    if info is None:
        import difflib
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

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Implement get_standings with multi-conference support"
```

---

## Task 13: tools.get_league_status

**Files:**
- Modify: `sports_mcp/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tools.py`:

```python
from sports_mcp.tools import get_league_status


async def test_get_league_status_in_season_with_games():
    payload = {
        "leagues": [
            {
                "season": {"type": {"name": "Regular Season"}},
                "calendar": [],
            }
        ],
        "events": [
            {
                "id": "1",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Lakers"}, "score": "0", "homeAway": "away"},
                            {"team": {"displayName": "Celtics"}, "score": "0", "homeAway": "home"},
                        ],
                        "status": {"type": {"state": "pre", "shortDetail": "7:30 PM ET"}},
                    }
                ],
            }
        ],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "The NBA is in the regular season" in s
    assert "Lakers" in s and "Celtics" in s


async def test_get_league_status_no_games():
    payload = {
        "leagues": [{"season": {"type": {"name": "Off Season"}}}],
        "events": [],
    }
    c = make_client(lambda r: httpx.Response(200, json=payload))
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "No games today" in s


async def test_get_league_status_unknown_league():
    c = make_client(lambda r: httpx.Response(200, json={}))
    try:
        s = await get_league_status(c, "Quidditch")
    finally:
        await c.aclose()
    assert "I don't recognize" in s


async def test_get_league_status_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = make_client(handler)
    try:
        s = await get_league_status(c, "NBA")
    finally:
        await c.aclose()
    assert "Couldn't reach ESPN" in s
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_tools.py -v
```

- [ ] **Step 3: Implement `get_league_status`**

Append to `sports_mcp/tools.py`:

```python
def _season_phrase(league_block: dict) -> str:
    season = (league_block.get("season") or {})
    type_block = season.get("type") or {}
    type_name = (type_block.get("name") or "").lower().strip()
    if not type_name or "off" in type_name:
        return "offseason"
    # Common ESPN values: 'preseason', 'regular season', 'postseason'
    return type_name


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
        short = (status.get("type") or {}).get("shortDetail") or ""
        # Strip TTS-unfriendly characters from the ESPN-supplied detail.
        short = short.replace("/", " ").replace("(", "").replace(")", "")
        if state == "in":
            tail = "in progress"
        elif state == "post":
            tail = "final"
        else:
            tail = f"scheduled {short}".strip()
        sentences.append(
            f"{away['team']['displayName']} at {home['team']['displayName']}, {tail}."
        )
    return " ".join(sentences)


async def get_league_status(client: ESPNClient, league: str) -> str:
    info = resolve_league(league)
    if info is None:
        import difflib
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

- [ ] **Step 4: Run tests and verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tool tests pass.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/tools.py tests/test_tools.py
git commit -m "Implement get_league_status combining season state and today's slate"
```

---

## Task 14: MCP server, SSE entry point

**Files:**
- Create: `sports_mcp/server.py`

- [ ] **Step 1: Write the server module**

Create `sports_mcp/server.py`:

```python
"""MCP server that exposes the four sports tools over SSE.

This module wires the tool functions from `sports_mcp.tools` into a FastMCP
instance and starts an SSE transport on 0.0.0.0:8000.

The exact FastMCP API for SSE evolves between mcp SDK versions. The
canonical pattern in 1.27 is `FastMCP(...).run(transport='sse', ...)`. If
that signature changes, the alternative is to obtain the Starlette ASGI app
via `.sse_app()` and run it with uvicorn directly.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from sports_mcp.espn import ESPNClient
from sports_mcp.tools import (
    get_league_status,
    get_live_score,
    get_next_game,
    get_standings,
)

log = logging.getLogger(__name__)


def build_server() -> tuple[FastMCP, ESPNClient]:
    client = ESPNClient()
    mcp = FastMCP("sports-mcp")

    @mcp.tool()
    async def live_score(team: str) -> str:
        """Current score and game state for a team's live game."""
        return await get_live_score(client, team)

    @mcp.tool()
    async def next_game(team: str) -> str:
        """The team's next scheduled game with opponent, time, and venue."""
        return await get_next_game(client, team)

    @mcp.tool()
    async def standings(league: str) -> str:
        """Standings for a league."""
        return await get_standings(client, league)

    @mcp.tool()
    async def league_status(league: str) -> str:
        """Season context plus today's slate for a league."""
        return await get_league_status(client, league)

    return mcp, client


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    mcp, _client = build_server()
    log.info("Starting sports-mcp on 0.0.0.0:8000 over SSE")
    # FastMCP 1.27 supports `run(transport='sse', host=..., port=...)`.
    mcp.run(transport="sse", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
uv run python -c "from sports_mcp.server import build_server; mcp, c = build_server(); print('tools:', list(mcp._tools.keys()) if hasattr(mcp, '_tools') else 'opaque')"
```

If the assertion about internal `_tools` attribute fails, replace it with a smoke check that just imports without error:

```bash
uv run python -c "from sports_mcp.server import build_server; build_server(); print('ok')"
```

Expected: prints `ok` (or `tools: [...]`).

- [ ] **Step 3: Adjust SSE invocation if FastMCP API differs**

If `mcp.run(transport="sse", host="0.0.0.0", port=8000)` raises a `TypeError` for unexpected kwargs, the FastMCP API in this SDK version uses a different surface. Switch to the Starlette app pattern:

```python
def main() -> None:
    import uvicorn  # add to dependencies in pyproject.toml if needed
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    mcp, _client = build_server()
    log.info("Starting sports-mcp on 0.0.0.0:8000 over SSE")
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=8000)
```

If switching to uvicorn, add `"uvicorn>=0.30.0"` to `dependencies` in `pyproject.toml` and re-run `uv sync`.

- [ ] **Step 4: Boot the server and probe the SSE endpoint**

In one terminal:

```bash
uv run sports-mcp
```

Expected log line: `Starting sports-mcp on 0.0.0.0:8000 over SSE`. Server stays running.

In a second terminal:

```bash
curl -sN -H "Accept: text/event-stream" http://127.0.0.1:8000/sse | head -5
```

Expected: SSE stream opens; you see at least one `event:` or initial framing line. (Do not expect a clean exit; press Ctrl-C after a moment.)

Stop the server with Ctrl-C in the first terminal.

- [ ] **Step 5: Commit**

```bash
git add sports_mcp/server.py pyproject.toml uv.lock 2>/dev/null || true
git commit -m "Add MCP server with SSE entry point on 0.0.0.0:8000"
```

(If `uvicorn` was added in Step 3, the `pyproject.toml`/`uv.lock` changes are part of this commit.)

---

## Task 15: Manual smoke script

**Files:**
- Create: `scripts/smoke.py`

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke.py`:

```python
"""Manual smoke test against live ESPN.

Hits scoreboard and standings for every supported league. Prints a
pass/fail table. Exits non-zero if any required endpoint fails.

Usage:
    uv run python scripts/smoke.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from sports_mcp.aliases import LEAGUE_REGISTRY


async def probe(client: httpx.AsyncClient, url: str) -> tuple[int, int]:
    try:
        r = await client.get(url, timeout=10.0)
        return r.status_code, len(r.content)
    except httpx.HTTPError as e:
        print(f"  ERROR fetching {url}: {e}", file=sys.stderr)
        return 0, 0


async def main() -> int:
    failures = 0
    print(f"{'league':<32} {'scoreboard':<12} {'standings':<12}")
    print("-" * 56)
    async with httpx.AsyncClient() as client:
        for li in LEAGUE_REGISTRY:
            sb_url = f"https://site.api.espn.com/apis/site/v2/sports/{li.slug}/scoreboard"
            st_url = f"https://site.api.espn.com/apis/v2/sports/{li.slug}/standings"
            sb_code, _ = await probe(client, sb_url)
            st_code, _ = await probe(client, st_url)
            sb_marker = "OK" if sb_code == 200 else f"FAIL {sb_code}"
            st_marker = "OK" if st_code == 200 else f"FAIL {st_code}"
            if sb_code != 200 or st_code != 200:
                failures += 1
            print(f"{li.name:<32} {sb_marker:<12} {st_marker:<12}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Run the smoke script**

```bash
uv run python scripts/smoke.py
```

Expected output (allow World Cup or Champions League scoreboard to be empty payloads but still 200):

```
league                           scoreboard   standings
--------------------------------------------------------
NFL                              OK           OK
NBA                              OK           OK
MLB                              OK           OK
NHL                              OK           OK
Premier League                   OK           OK
MLS                              OK           OK
World Cup                        OK           OK
Champions League                 OK           OK
```

If any row reports FAIL, investigate before proceeding. The likely cause is a stale slug; verify against [pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API) and update `LEAGUE_REGISTRY` if needed.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke.py
git commit -m "Add manual smoke script for live ESPN slug verification"
```

---

## Task 16: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the README**

Replace `README.md` with:

```markdown
# sports-mcp

An MCP server that wraps ESPN's public API and exposes four sports tools to
Home Assistant over SSE.

## Tools

- `live_score(team)` — current score and game state for a team's live game.
- `next_game(team)` — opponent, date, time, and venue of a team's next game.
- `standings(league)` — TTS-safe standings table for a league.
- `league_status(league)` — season context plus today's slate.

Inputs are friendly names (e.g., "Lakers", "Premier League"); the server
resolves them to ESPN identifiers internally. Outputs are TTS-safe natural
language (no parens, slashes, or ampersands).

## Supported leagues

NFL, NBA, MLB, NHL, English Premier League, MLS, FIFA World Cup,
UEFA Champions League.

## Run

```bash
uv sync --group dev
uv run sports-mcp
```

The server binds on `0.0.0.0:8000` over SSE.

## Home Assistant configuration

Add the MCP client integration in Home Assistant. Configure the SSE URL:

```
http://<sports-mcp-host>:8000/sse
```

No authentication is required; deploy on a trusted LAN.

## Development

Run tests:

```bash
uv run pytest -v
```

Smoke-test live ESPN slugs:

```bash
uv run python scripts/smoke.py
```

Re-harvest team data when leagues change rosters:

```bash
uv run python scripts/harvest_teams.py > sports_mcp/teams_data.py
```

## Limitations

ESPN's API is undocumented and unsupported. Endpoints can change without
notice. The smoke script catches slug-level breakage; the test suite uses
captured fixtures and won't notice schema changes.
```

- [ ] **Step 2: Verify the file renders**

```bash
cat README.md | head -30
```

Confirm it's the new content and not the original empty file.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document tools, run instructions, and Home Assistant setup"
```

---

## Task 17: Final integration check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass. Approximate count: 5 (cache) + 17 (aliases) + ~22 (format) + 7 (espn) + 17 (tools) ≈ 68 tests.

- [ ] **Step 2: Boot the server and tail logs**

```bash
uv run sports-mcp &
SERVER_PID=$!
sleep 2
curl -sN -H "Accept: text/event-stream" http://127.0.0.1:8000/sse | head -5
kill $SERVER_PID
```

Expected: server starts cleanly, SSE endpoint responds with at least one event line.

- [ ] **Step 3: Run the smoke script one more time**

```bash
uv run python scripts/smoke.py
```

Expected: all 8 leagues report OK / OK.

- [ ] **Step 4: Final commit (only if any cleanup happened)**

```bash
git status
```

If clean, no commit needed. If anything was tweaked above, commit it with a descriptive message.

---

## Done

The server is ready to deploy. Configure the Home Assistant MCP client integration to point at `http://<host>:8000/sse` and verify with a voice query like "what's going on in the NBA?".
