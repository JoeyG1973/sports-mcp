# sports-mcp

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP 1.27+](https://img.shields.io/badge/mcp-1.27+-8A2BE2.svg)](https://modelcontextprotocol.io/)

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

The server binds on `0.0.0.0:8000` over SSE by default. Override with
`--host`/`--port` flags or the `SPORTS_MCP_HOST`/`SPORTS_MCP_PORT`
environment variables (CLI flags take precedence):

```bash
uv run sports-mcp --host 127.0.0.1 --port 9000
SPORTS_MCP_HOST=127.0.0.1 SPORTS_MCP_PORT=9000 uv run sports-mcp
```

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

## License

Apache License 2.0 — see [LICENSE](LICENSE).
