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
