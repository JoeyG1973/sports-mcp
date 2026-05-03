from sports_mcp.aliases import (
    LEAGUE_REGISTRY,
    LeagueInfo,
    resolve_league,
    TeamMatch,
    TeamMatchAmbiguous,
    TeamMatchNone,
    TeamMatchOne,
    resolve_team,
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


def test_resolve_team_single_match():
    m = resolve_team("Lakers")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"
    assert m.team.league_slug == "basketball/nba"


def test_resolve_team_case_insensitive():
    assert resolve_team("LAKERS").__class__ is TeamMatchOne
    assert resolve_team("lakers").__class__ is TeamMatchOne


def test_resolve_team_by_full_name():
    m = resolve_team("Los Angeles Lakers")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"


def test_resolve_team_by_abbreviation():
    m = resolve_team("LAL")
    assert isinstance(m, TeamMatchOne)
    assert m.team.abbreviation == "LAL"


def test_resolve_team_ambiguous_giants():
    m = resolve_team("Giants")
    assert isinstance(m, TeamMatchAmbiguous)
    slugs = {t.league_slug for t in m.teams}
    assert "football/nfl" in slugs
    assert "baseball/mlb" in slugs


def test_resolve_team_prefer_league_breaks_tie():
    m = resolve_team("Giants", prefer_league="basketball/nba")
    # Giants is not in NBA, so still ambiguous, falls back
    assert isinstance(m, TeamMatchAmbiguous)
    m2 = resolve_team("Giants", prefer_league="football/nfl")
    assert isinstance(m2, TeamMatchOne)
    assert m2.team.league_slug == "football/nfl"


def test_resolve_team_unknown_with_suggestions():
    m = resolve_team("Lkaers")
    assert isinstance(m, TeamMatchNone)
    # Suggestions should include something close to Lakers
    suggestion_text = " ".join(m.suggestions).lower()
    assert "laker" in suggestion_text


def test_resolve_team_unknown_no_close_match():
    m = resolve_team("zzzzzzzzzzzz")
    assert isinstance(m, TeamMatchNone)
    assert m.suggestions == []
