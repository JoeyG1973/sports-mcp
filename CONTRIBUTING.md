# Contributing

Thanks for your interest in `sports-mcp`. This is a small project, so the
process is light.

## Dev setup

```bash
git clone https://github.com/JoeyG1973/sports-mcp.git
cd sports-mcp
uv sync --group dev
```

You'll need Python 3.13 or newer.

## Run the test suite

```bash
uv run pytest -v
```

The suite uses captured ESPN fixtures and runs in well under a second.

## Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

Both must pass in CI before a PR can merge.

## Smoke test against live ESPN

```bash
uv run python scripts/smoke.py
```

This hits ESPN's real API. Run it before opening a PR if your change
touches `sports_mcp/espn.py` or any URL slugs.

## Pull requests

1. Create a topic branch from `main` (`feat/...`, `fix/...`, `docs/...`).
2. Add or update tests for any behavior change. Fixture-driven tests are
   preferred — see `tests/fixtures/` and `tests/conftest.py`.
3. Run `uv run pytest` and the lint commands locally.
4. Open the PR — CI will run automatically.
5. Merges happen once CI is green. No required reviewers, but the maintainer
   may request changes before merging.

## What's in scope

- Bug fixes in the four existing tools (`live_score`, `next_game`,
  `standings`, `league_status`).
- TTS-output improvements (no parens, slashes, or ampersands; natural
  phrasing).
- Better handling of edge cases in ESPN's responses (offseason, postseason,
  empty payloads, etc.).
- Adding leagues that ESPN's API already exposes.

## What's out of scope

- Authentication or multi-tenant features. This server is designed to run
  on a trusted LAN.
- Wrapping APIs other than ESPN's public site/v2 endpoints.
- UI or web front-ends — clients are MCP-aware (Home Assistant Voice,
  Claude Desktop, etc.).

## Reporting bugs and requesting features

Use the issue templates on the repository's **Issues** tab. For security
issues, see [`SECURITY.md`](SECURITY.md) instead.
