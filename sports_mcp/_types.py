"""Shared frozen dataclasses for the sports_mcp package.

These types are kept in their own module to avoid circular imports between
aliases.py (the resolvers) and teams_data.py (the auto-generated team list).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueInfo:
    """One supported league."""

    name: str
    sport: str
    slug: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class TeamInfo:
    """One team within a league."""

    name: str
    league_slug: str
    espn_id: str
    abbreviation: str
    aliases: tuple[str, ...]
