# sports-mcp

[![tests](https://github.com/JoeyG1973/sports-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/JoeyG1973/sports-mcp/actions/workflows/tests.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP 1.27+](https://img.shields.io/badge/mcp-1.27+-8A2BE2.svg)](https://modelcontextprotocol.io/)

Ask Home Assistant Voice "what's the score of the Lakers game?" and have it
answer in plain English. `sports-mcp` is a small MCP server that wraps
ESPN's public API and exposes four read-only tools tuned for text-to-speech:
no parens, no slashes, no ampersands, no abbreviations a TTS engine
mispronounces — just sentences a voice assistant can read back cleanly.

## What it does

Four tools, all addressed by friendly names ("Lakers", "Premier League"):

| Tool | What it returns |
|---|---|
| `live_score(team)` | The current score and game state for a team's live game. |
| `next_game(team)` | The team's next scheduled game with opponent, date, time, and venue. |
| `standings(league)` | A TTS-safe standings table with division-winner and best-record annotations, plus offseason / postseason context. |
| `league_status(league)` | Today's slate plus the season phase (regular season, playoffs, offseason, tournament). |

The server resolves friendly names to ESPN identifiers internally, returns
fuzzy suggestions on near-misses, and falls back gracefully when ESPN
returns empty payloads or when a league is between seasons.

## Example output

These are real strings the server emits (lifted from the test fixtures):

```
> live_score("Lakers")
Lakers 89, Celtics 91, fourth quarter, 2 minutes 34 seconds remaining.

> next_game("Lakers")
The Los Angeles Lakers don't have a live game yet.
They host the Boston Celtics today at 8 PM.

> standings("Eastern Conference")
Eastern Conference.
Boston Celtics first at 52 wins and 18 losses.
Milwaukee Bucks second at 48 wins and 22 losses.

> league_status("NBA")
The NBA is in the regular season, week 12.
Lakers at Celtics, fourth quarter. Heat at Knicks, scheduled 7 30 PM.

> league_status("NFL")        # offseason
The NFL is in the offseason. No games today.

> live_score("Giants")        # ambiguous
Giants is ambiguous. Did you mean the NFL Giants or the MLB Giants?

> live_score("Lkaers")        # typo
I don't recognize Lkaers. Did you mean lakers or clippers?
```

## Supported leagues

NFL, NBA, MLB, NHL, English Premier League, MLS, FIFA World Cup,
UEFA Champions League.

## Quickstart

```bash
git clone https://github.com/JoeyG1973/sports-mcp.git
cd sports-mcp
uv sync --group dev
uv run sports-mcp
```

Requires Python 3.13+ and the [uv](https://github.com/astral-sh/uv)
package manager. The server binds on `0.0.0.0:8000` over SSE by default.

### Custom bind address

Override with `--host`/`--port` flags or the `SPORTS_MCP_HOST` /
`SPORTS_MCP_PORT` environment variables (CLI flags take precedence):

```bash
uv run sports-mcp --host 127.0.0.1 --port 9000
SPORTS_MCP_HOST=127.0.0.1 SPORTS_MCP_PORT=9000 uv run sports-mcp
```

## Home Assistant configuration

1. In Home Assistant, install the **Model Context Protocol** integration
   (Settings → Devices & Services → Add Integration → search "MCP").
2. Configure it with the SSE URL of your `sports-mcp` instance:

   ```
   http://<sports-mcp-host>:8000/sse
   ```

3. Expose the integration to **Assist** so Voice can call the tools.

The four tools then become callable by the voice assistant. No
authentication is required — deploy on a trusted LAN and do not expose
the SSE port to the public internet.

## Running as a systemd service (Linux)

A starter unit file lives at [`deploy/sports-mcp.service`](deploy/sports-mcp.service).
It's intentionally minimal — runs as root, logs to journald (the default),
no sandboxing. Suitable for a home-lab deployment on a trusted LAN.

```bash
# 1. Clone to /opt/sports-mcp (or edit WorkingDirectory in the unit file).
sudo git clone https://github.com/JoeyG1973/sports-mcp.git /opt/sports-mcp
cd /opt/sports-mcp

# 2. Pre-build the venv.
sudo uv sync

# 3. Install and start the unit.
sudo cp deploy/sports-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sports-mcp

# 4. Tail logs.
journalctl -u sports-mcp -f
```

If `uv` lives somewhere other than `/usr/local/bin/uv`, update `ExecStart`
in the unit file (`command -v uv` shows the path).

## Compatibility

| Component | Tested with |
|---|---|
| Python | 3.13 |
| MCP SDK | 1.27+ |
| ESPN API | site/v2 (public, undocumented) |

## Development

```bash
uv run pytest -v               # 130 tests, runs in well under a second
uv run ruff check .            # lint
uv run ruff format --check .   # format check
```

Smoke-test against live ESPN (catches slug-level breakage):

```bash
uv run python scripts/smoke.py
```

Re-harvest team data when leagues change rosters:

```bash
uv run python scripts/harvest_teams.py > sports_mcp/teams_data.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR flow.

## Limitations

ESPN's API is undocumented and unsupported. Endpoints can change without
notice. The smoke script catches slug-level breakage; the test suite uses
captured fixtures and won't notice schema changes.

This project is not affiliated with or endorsed by ESPN.

## Security

See [SECURITY.md](SECURITY.md) for the threat model and how to report
vulnerabilities privately.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
