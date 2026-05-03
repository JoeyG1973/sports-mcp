# sports-mcp Design

**Date:** 2026-05-02
**Status:** Draft, pending user review

## Summary

A Python MCP server that wraps ESPN's undocumented public API and exposes four
tools to a Home Assistant MCP client. The server runs over SSE on
`0.0.0.0:8000`, accepts friendly team and league names (e.g., "Lakers", "Premier
League"), resolves them to ESPN slugs and IDs internally, and returns
TTS-safe natural-language strings.

## Goals

- Let a Home Assistant voice assistant answer everyday sports questions ("did
  the Lakers win?", "when do the Yankees play next?", "what's going on in the
  NBA?") without forcing the user or LLM to know ESPN's URL conventions.
- Stay within the bounds of polite use of ESPN's unofficial API: cache
  short-lived responses, time out fast, never poll on a hot loop.
- Be small enough to read in one sitting and easy to debug from logs.

## Non-goals

- Not a fantasy / betting / projections engine. No player-level stats, lines,
  or props in v1.
- No persistence layer, no database, no metrics store.
- No auth on the MCP server itself. The deployment assumption is that Home
  Assistant and the server share a trusted LAN.
- No NASCAR or other racing series in v1. The four-tool contract is built
  around two-team events; racing breaks the model and is deferred.
- No live integration tests against ESPN. Slug verification happens via a
  manual smoke script, not CI.

## Supported leagues

Eight leagues, all verified live against ESPN on 2026-05-02:

| League                  | Sport      | ESPN slug              |
| ----------------------- | ---------- | ---------------------- |
| NFL                     | football   | `football/nfl`         |
| NBA                     | basketball | `basketball/nba`       |
| MLB                     | baseball   | `baseball/mlb`         |
| NHL                     | hockey     | `hockey/nhl`           |
| English Premier League  | soccer     | `soccer/eng.1`         |
| Major League Soccer     | soccer     | `soccer/usa.1`         |
| FIFA World Cup          | soccer     | `soccer/fifa.world`    |
| UEFA Champions League   | soccer     | `soccer/uefa.champions`|

The World Cup is idle outside its tournament windows; the server returns a
TTS-safe "no active competition" string in that case.

## Tool contracts

All inputs are simple strings. All outputs are TTS-safe natural-language
strings (see "TTS-safe output rules" below). Tools never raise to the MCP
framework; every error path returns a string.

### `get_live_score(team: str) -> str`

Returns the current score and game state if the team has a game in progress,
otherwise a "no live game" string.

Examples:
- `get_live_score("Lakers")` → `"Lakers 89, Celtics 91, fourth quarter, 2 minutes 34 seconds remaining."`
- `get_live_score("Yankees")` → `"The Yankees do not have a live game right now."`

### `get_next_game(team: str) -> str`

Returns the team's next scheduled game.

Examples:
- `get_next_game("Lakers")` → `"The Lakers play the Celtics on Thursday at 8 PM eastern at TD Garden."`
- `get_next_game("Arsenal")` → `"Arsenal does not have a scheduled game on the calendar."`

### `get_standings(league: str) -> str`

Returns a TTS-safe summary of the standings for that league. For
multi-conference leagues (NBA, NFL, NHL, MLB), the summary covers each
conference. For single-table leagues (EPL, MLS), one table. For the Champions
League and World Cup, the response reflects whatever phase ESPN currently
returns: a group-stage table when applicable, or a phrased description if
ESPN returns a knockout-bracket stub instead of a table (e.g.,
`"The Champions League is in the round of 16."`).

Example (truncated):
- `get_standings("NBA")` → `"Eastern Conference. Boston Celtics first at 52 wins and 18 losses. Milwaukee Bucks second at 48 wins and 22 losses. ..."`

### `get_league_status(league: str) -> str`

Combines season context and today's slate into a single response.

Example:
- `get_league_status("NBA")` → `"The NBA is in the regular season, week 12. Five games today. Lakers are at the Celtics, started 30 minutes ago, fourth quarter. Heat at Knicks, scheduled 7 30 PM eastern. ..."`

## Architecture

### Repo layout

```
sports-mcp/
├── pyproject.toml          # console script: sports-mcp = "sports_mcp.server:main"
├── README.md               # run + Home Assistant config instructions
├── sports_mcp/
│   ├── __init__.py
│   ├── __main__.py         # python -m sports_mcp
│   ├── server.py           # MCP server, tool registration, SSE bind 0.0.0.0:8000
│   ├── espn.py             # async httpx ESPN client, two base paths
│   ├── cache.py            # tiny TTL cache, per-key expiry
│   ├── aliases.py          # league + team alias maps + resolve functions
│   ├── tools.py            # four tool implementations, orchestration only
│   └── format.py           # TTS-safe formatters
├── scripts/
│   └── smoke.py            # manual: hit live ESPN, verify all slugs respond
└── tests/
    ├── conftest.py
    ├── fixtures/           # canned ESPN JSON per endpoint per league
    └── test_*.py
```

The placeholder `main.py` from `uv init` is removed; the entry point becomes
`sports_mcp.server:main` (registered as a console script in `pyproject.toml`).

### Component responsibilities

**`server.py`** — instantiates the MCP server (using whichever `mcp` SDK
surface is cleanest in 1.27, likely `FastMCP` for tool registration), wires
the four tool functions from `tools.py`, mounts SSE transport on
`0.0.0.0:8000`, and exposes a `main()` entry point. No business logic. Owns
the lifecycle of the shared `ESPNClient`.

**`espn.py`** — `ESPNClient` class wrapping a single `httpx.AsyncClient`.
Methods: `scoreboard(league_slug)`, `team_schedule(league_slug, team_id)`,
`standings(league_slug)`. Each method picks the correct base URL (see "ESPN
endpoint conventions"), constructs the path, hits the cache, falls through to
HTTP, parses JSON, returns dicts. `httpx` timeout set to `8.0` seconds.

**`cache.py`** — `TTLCache` class with `get(key)` and
`set(key, value, ttl_seconds)`. Backed by a dict mapping key →
`(value, expires_at_monotonic)`. Lazy expiry on read; no background eviction.
Per-call TTL passed by the caller. No external dependency.

**`aliases.py`** — pure data plus resolver functions:
- `LEAGUES: dict[str, LeagueInfo]` — alias keys (lowercased) →
  `LeagueInfo(name, sport, slug, kind)`. Multiple aliases point to the same
  `LeagueInfo` (e.g., `"epl"`, `"premier league"`, `"english premier league"`
  all map to the EPL entry).
- `TEAMS: dict[str, list[TeamInfo]]` — normalized alias key →
  `[TeamInfo(name, league_slug, espn_id, abbreviation), ...]`. The list form
  handles cross-league collisions like "Giants" (NYG and SFG).
- `resolve_league(text: str) -> LeagueInfo | None`
- `resolve_team(text: str, prefer_league: str | None = None) -> TeamMatch`
  where `TeamMatch` is a small union type representing one of: single match,
  ambiguous (multiple matches), unknown (no match), or unknown-with-suggestions
  (fuzzy candidates).

Aliases are stored as inline Python dicts, not JSON. Reasoning: they are
reviewed in PRs alongside code changes, are loaded at module import, and rarely
change. Estimated size: 8 leagues with ~5 aliases each, ~250 teams with
~3 aliases each. Well under 1000 lines of structured data.

**`tools.py`** — four async functions, each takes the raw caller string, runs
through `aliases`, calls `ESPNClient`, formats the result via `format.py`, and
returns a string. No HTTP logic, no formatting logic — just orchestration and
error handling.

**`format.py`** — pure functions that produce TTS-safe strings:
- `score_line(home_name, home_score, away_name, away_score, period, clock)`
- `game_time(iso_datetime, venue)`
- `standings_block(rows)`
- `league_status_block(season_state, today_events)`
- `ambiguity_message(team_text, candidates)`
- `unknown_team_message(team_text, suggestions)`
- `unknown_league_message(league_text, suggestions)`
- Number-to-words helpers (e.g., `2:34` → `"2 minutes 34 seconds remaining"`,
  `7:30 PM ET` → `"7 30 PM eastern"`).

### Data flow example: `get_live_score("Lakers")`

1. `tools.get_live_score("Lakers")` calls `aliases.resolve_team("Lakers")`.
2. Resolver returns a single `TeamInfo(name="Los Angeles Lakers",
   league_slug="basketball/nba", espn_id="13", abbreviation="LAL")`.
3. Tool calls `ESPNClient.scoreboard("basketball/nba")`. TTL: 15 seconds.
4. Cache miss. Client GETs
   `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard`,
   parses JSON, stores in cache, returns dict.
5. Tool scans `events` for one whose competitors include team id `13`.
6. If found and `status.type.state == "in"`, build prose via
   `format.score_line(...)` and return.
7. If found but `state == "pre"`, return "Lakers don't have a live game right
   now, but they play [opponent] at [time]."
8. If found but `state == "post"`, return "Lakers don't have a live game right
   now. Their last game ended..." (final score).
9. If not found, return "Lakers do not have a live game right now."

### ESPN endpoint conventions

ESPN's hidden API exposes two base paths that we route between based on
endpoint type:

- **Scoreboard, teams, schedule:** `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/...`
- **Standings:** `https://site.api.espn.com/apis/v2/sports/{sport}/{league}/standings`
  (the `site` segment is dropped). Hitting `/apis/site/v2/.../standings`
  returns a stub.

`ESPNClient` encodes this routing internally. Callers pass the league slug; the
client picks the base URL.

Useful query parameters used internally (not exposed as tool inputs):
- `dates=YYYYMMDD` for "games on a specific date" (used to scope today's slate
  in `get_league_status`).
- `seasontype=1|2|3` for pre/regular/post filtering.
- `limit=N` to cap result counts where applicable.

### Season state for `get_league_status`

Season context is derived from the scoreboard response itself, not a separate
endpoint. The scoreboard payload includes `leagues[0].season` (year, current
season type: pre/reg/post) and `leagues[0].calendar` (week list with start/end
dates). One scoreboard call yields both today's slate and the season context.

For the World Cup outside a tournament window, `events` will be empty and the
season metadata will reflect a non-active state; the formatter produces:
`"The World Cup is not currently in tournament play. The next tournament is
scheduled for [date]."` (when ESPN provides a scheduled date; otherwise just
"is not currently in tournament play").

## Caching

A small in-memory TTL cache keyed by the full request URL. TTLs:

| Endpoint        | TTL     | Reasoning                                              |
| --------------- | ------- | ------------------------------------------------------ |
| Scoreboard      | 15 s    | Live scores need to feel current; protects from polling. |
| Team schedule   | 300 s   | Schedules change rarely.                               |
| Standings       | 300 s   | Updates after games end, never minute-to-minute.       |

The cache is a process-local dict; restarts clear it. No persistence.

## TTS-safe output rules

Every string returned to MCP is read by Home Assistant TTS pipelines, often
without LLM rewriting. The following rules apply uniformly:

- No parentheses, no slashes, no ampersands.
- No `vs.` — use `"versus"` or rephrase (`"the Lakers play the Celtics"`).
- No `@` — use `"at"`.
- No score abbreviations like `52-18` — write `"52 wins and 18 losses"`.
- No clock abbreviations like `Q4 2:34` — write
  `"fourth quarter, 2 minutes 34 seconds remaining"`.
- No timezone abbreviations like `ET` — write `"eastern"`.
- No half-formed punctuation; sentences end with periods.

`format.py` enforces these rules; tests assert exact strings on representative
cases (see "Testing").

## Error handling

Every tool returns a TTS-safe string for every failure mode. Exceptions never
propagate to the MCP framework.

| Failure                                  | Behavior                                                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Unknown league after alias lookup        | `"I don't recognize 'Foo'. Did you mean Bar, Baz, or Qux?"` (top 3 fuzzy matches via `difflib.get_close_matches`) |
| Unknown team after alias lookup          | Same shape, scoped to teams.                                                                      |
| Ambiguous team name                      | `"Giants is ambiguous. Did you mean the NFL Giants or the MLB Giants?"`                            |
| ESPN HTTP timeout, 5xx, connection error | `"Couldn't reach ESPN, try again in a moment."` Logged at WARNING with URL and status.            |
| ESPN 4xx (bad slug, deprecated endpoint) | Same user-facing message. Logged at ERROR — indicates a slug map bug.                             |
| Empty result (no live, no upcoming, etc.)| Per-tool prose: see tool contracts above.                                                          |
| Out-of-season league for status query    | `"The NFL is in the offseason. The next season starts on September 5th."` (when start known)      |

## Logging

`logging` to stdout at INFO level. One line per tool call:
`tool=get_live_score arg="Lakers" resolved="LAL/basketball/nba/id=13" latency_ms=147 cache=hit`.
ESPN HTTP errors at WARNING. Slug-map bugs (4xx from ESPN) at ERROR.

No structured logging library; standard `logging` module suffices for a
single-process server.

## Time and dates

ESPN returns event times as UTC ISO 8601 timestamps. The server converts to
the host's local timezone (via Python's `datetime.astimezone()` with no
argument) when rendering prose. Rationale: Home Assistant's host time is
typically configured to the user's local timezone, so this is the right
default with zero configuration. If the deployment requires a different zone
later, the conversion is one place to change.

Date phrasing:
- Within the next 7 days, use the weekday name: `"Thursday at 8 PM"`.
- Beyond 7 days, use the date: `"May 12 at 8 PM"`.
- "Today" and "tomorrow" are used when applicable instead of the weekday name.

## Configuration

None in v1. The bind address (`0.0.0.0:8000`), TTLs, and timeouts are
constants in code. If we need to vary them later, environment variables are
the obvious next step, but YAGNI for now.

## Dependencies

- `mcp >= 1.27.0` — already in `pyproject.toml`.
- `httpx >= 0.28.1` — already in `pyproject.toml`.
- Dev: `pytest`, `pytest-asyncio`. Add to `[dependency-groups.dev]` in
  `pyproject.toml`.

## Testing

Pytest with `pytest-asyncio`. One test file per module. No live HTTP in CI.

- **`test_aliases.py`** — happy paths (`"NFL"`, `"premier league"`, `"Lakers"`),
  case insensitivity, ambiguity detection (`"Giants"` returns both NYG and
  SFG), fuzzy suggestions (`"Lkaers"` → suggestion includes "Lakers"), missing
  aliases.
- **`test_cache.py`** — set/get round-trip, expiry past TTL, key isolation,
  monotonic-clock semantics.
- **`test_espn.py`** — `httpx.MockTransport` injects canned JSON from
  `tests/fixtures/`. Asserts URL construction (especially the
  `/apis/site/v2/` vs `/apis/v2/` split), cache hits and misses, timeout
  handling.
- **`test_tools.py`** — for each of the four tools: one happy path, one
  empty-result path, one "ESPN unreachable" path (mock raises). Assert exact
  prose strings to lock the TTS-safe format.
- **`test_format.py`** — pure unit tests; assert no parens, no slashes, no
  abbreviations slip through across a representative sample of inputs.

Fixtures: real ESPN JSON captured for one league per request type:
- NBA scoreboard (live game in progress)
- NBA scoreboard (no games today)
- MLB team schedule
- EPL standings
- NFL scoreboard with season metadata for status testing

About 6 fixture files total, ~1 MB.

`scripts/smoke.py` is a manual integration script: hits real ESPN for all 8
slugs across all three endpoint types, prints a pass/fail table. Run by hand
before releasing changes; not part of CI.

## Deployment

`uv run sports-mcp` (after the console script is registered) starts the
server. Home Assistant's MCP client integration is configured with SSE
transport pointing at `http://<host>:8000/sse`.

A systemd unit or container is out of scope for this spec; the user runs the
process however they like.

## Open risks

- **ESPN can change endpoints without notice.** Mitigation: smoke script,
  graceful errors, easy-to-update slug map. No further mitigation feasible
  without a paid official API.
- **Rate-limiting is unknowable.** Mitigation: TTL cache plus an 8-second
  request timeout. We will see warnings in logs if ESPN starts returning
  errors and can react.
- **Alias coverage gaps.** Less-common nicknames may not resolve on first try.
  Mitigation: fuzzy fallback for unknown teams, plus the alias map is a single
  file users can extend.
