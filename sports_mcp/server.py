"""MCP server that exposes the four sports tools over SSE.

This module wires the tool functions from `sports_mcp.tools` into a FastMCP
instance and starts an SSE transport. The bind address defaults to
0.0.0.0:8000 and can be overridden via --host/--port flags or the
SPORTS_MCP_HOST/SPORTS_MCP_PORT environment variables (CLI wins).

The exact FastMCP API for SSE evolves between mcp SDK versions. The
canonical pattern in 1.27 is `FastMCP(...).run(transport='sse', ...)`. If
that signature changes, the alternative is to obtain the Starlette ASGI app
via `.sse_app()` and run it with uvicorn directly.
"""
from __future__ import annotations

import argparse
import logging
import os

from mcp.server.fastmcp import FastMCP

from sports_mcp.espn import ESPNClient
from sports_mcp.tools import (
    get_league_status,
    get_live_score,
    get_next_game,
    get_standings,
)

log = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000


def build_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> tuple[FastMCP, ESPNClient]:
    client = ESPNClient()
    mcp = FastMCP("sports-mcp", host=host, port=port)

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
    parser = argparse.ArgumentParser(prog="sports-mcp")
    parser.add_argument(
        "--host",
        default=os.environ.get("SPORTS_MCP_HOST", DEFAULT_HOST),
        help="Bind address (env: SPORTS_MCP_HOST, default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SPORTS_MCP_PORT", DEFAULT_PORT)),
        help="Bind port (env: SPORTS_MCP_PORT, default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    mcp, _client = build_server(host=args.host, port=args.port)
    log.info("Starting sports-mcp on %s:%d over SSE", args.host, args.port)
    # FastMCP 1.27: host/port are constructor args; run() only takes transport.
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
