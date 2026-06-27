from sports_mcp.aliases import (
    LEAGUE_REGISTRY,
    TeamMatchAmbiguous,
    TeamMatchNone,
    TeamMatchOne,
    resolve_league,
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


def test_resolve_arsenal_resolves_to_premier_league():
    m = resolve_team("Arsenal")
    assert isinstance(m, TeamMatchOne)
    assert m.team.league_slug == "soccer/eng.1"


def _assert_usmnt(m):
    assert isinstance(m, TeamMatchOne), m
    assert m.team.espn_id == "660"
    assert m.team.league_slug == "soccer/fifa.world"


def test_resolve_team_usa_baseline_still_works():
    _assert_usmnt(resolve_team("USA"))
    _assert_usmnt(resolve_team("United States"))


def test_resolve_team_usmnt_acronym():
    _assert_usmnt(resolve_team("USMNT"))


def test_resolve_team_national_team_full_name():
    _assert_usmnt(resolve_team("United States Men's National Team"))


def test_resolve_team_national_team_full_name_no_apostrophe():
    _assert_usmnt(resolve_team("United States Mens National Team"))


def test_resolve_team_curated_nicknames():
    _assert_usmnt(resolve_team("US"))
    _assert_usmnt(resolve_team("Team USA"))


def test_resolve_team_strips_leading_the_article():
    _assert_usmnt(resolve_team("the USA"))


def test_resolve_team_generic_national_team_phrase_any_country():
    # The generic "<country> national team" phrasing works for any country,
    # not just hand-curated ones.
    m = resolve_team("Brazil national team")
    assert isinstance(m, TeamMatchOne)
    assert m.team.league_slug == "soccer/fifa.world"
    assert m.team.name == "Brazil"


def test_resolve_team_curly_apostrophe_normalized():
    _assert_usmnt(resolve_team("United States Men’s National Team"))


def test_resolve_team_usa_natural_voice_variants():
    # Surface forms the voice model emits for the USMNT.
    _assert_usmnt(resolve_team("USA mens soccer"))
    _assert_usmnt(resolve_team("US mens national team"))
    _assert_usmnt(resolve_team("USA men's soccer team"))
    _assert_usmnt(resolve_team("United States national soccer team"))


def test_resolve_team_no_descriptive_suffix_pollution():
    # The bug: "US mens national team" fuzzy-locked onto the "national team"
    # suffix and offered unrelated countries. It must resolve, not suggest.
    m = resolve_team("US mens national team")
    assert isinstance(m, TeamMatchOne)
    assert m.team.espn_id == "660"


def test_resolve_team_bare_national_team_phrase_no_bogus_country():
    # A phrase with no country must NOT resolve to or suggest a random country.
    m = resolve_team("national team")
    assert isinstance(m, TeamMatchNone)
    assert not any("national team" in s for s in m.suggestions)


def _assert_country(m, name):
    assert isinstance(m, TeamMatchOne), m
    assert m.team.league_slug == "soccer/fifa.world"
    assert m.team.name == name


def test_resolve_team_country_alternate_cabo_verde():
    _assert_country(resolve_team("Cabo Verde"), "Cape Verde")


def test_resolve_team_country_alternate_cote_divoire():
    _assert_country(resolve_team("Côte d'Ivoire"), "Ivory Coast")
    _assert_country(resolve_team("Cote d'Ivoire"), "Ivory Coast")


def test_resolve_team_country_alternate_korea_republic():
    _assert_country(resolve_team("Korea Republic"), "South Korea")


def test_resolve_team_country_alternate_turkey():
    _assert_country(resolve_team("Turkey"), "Türkiye")
    _assert_country(resolve_team("Turkiye"), "Türkiye")


def test_resolve_team_country_alternate_czech_republic():
    _assert_country(resolve_team("Czech Republic"), "Czechia")


def test_resolve_team_country_name_still_resolves():
    # Regression: canonical country names and other countries' descriptive
    # phrasings keep working.
    _assert_country(resolve_team("Spain"), "Spain")
    _assert_country(resolve_team("Cape Verde"), "Cape Verde")
    _assert_country(resolve_team("Brazil national team"), "Brazil")
