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
