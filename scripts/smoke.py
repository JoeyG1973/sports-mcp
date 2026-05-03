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
