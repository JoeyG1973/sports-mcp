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
