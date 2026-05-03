# `get_standings` season awareness

**Date:** 2026-05-02
**Status:** Draft, pending user review
**Supersedes / extends:** [Initial sports-mcp design](2026-05-02-sports-mcp-design.md)

## Summary

`get_standings` currently produces the same response shape regardless of
where a league is in its yearly cycle. It works during regular season but
reads as confusing or misleading during postseason ("here's a standings
table, no signal that playoffs are happening") and offseason ("here's a
standings table, no signal that this is last season's results"). This
change adds two layered signals to the response:

1. A phase prefix announcing offseason or postseason when applicable.
2. A per-team playoff-qualification annotation for leagues whose standings
   include a clinch indicator.

Regular-season output is unchanged — this is a strict superset.

## Motivation

Three real-world cases that today produce confusing answers:

1. Asking about the NFL in May. The Super Bowl is months past. The current
   response gives the regular-season standings as if they were live, with
   no acknowledgment that the season is over. A user listening through TTS
   reasonably believes the answer is current.

2. Asking about the NHL during playoffs. Eight Eastern Conference teams
   have already been eliminated. The current response lists them at their
   regular-season position with no signal that they are out.

3. The same in NBA, MLB, MLS during their respective postseasons.

Each is a case where ESPN already exposes the data — the standings
response carries season metadata and per-team clinch indicators — and the
tool is throwing it away.

## Goals

- Detect "is the league past its regular season" without an extra round
  trip when the standings response carries enough signal.
- Detect "is the league in offseason" using a stable signal that does not
  depend on `season.type.id` (which is unreliable in NFL's offseason).
- Annotate qualified vs. eliminated teams when ESPN's standings carry the
  per-team clinch indicator.
- Leave regular-season behavior byte-for-byte unchanged.

## Non-goals

- No new tools, no new ESPN endpoints, no new dependencies.
- No detail beyond `qualified` / `did not qualify` in v1. We do not
  distinguish "won the division" (`y`) from "won the conference" (`z`)
  from a generic playoff berth (`x`). All three become "qualified". We
  do not surface elimination rounds (lost in wild card / divisional /
  conference final). We do not name the champion.
- No special handling for EPL relegation, World Cup tournament structure,
  or Champions League knockouts. These leagues lack a clinch indicator in
  their standings response and will simply not get per-team annotations.
  They can still get the offseason prefix.
- No annotation for individual sports (none currently in scope; NASCAR is
  out of scope per prior design).

## Detection rules

ESPN's standings endpoint returns a `season` block with `startDate`,
`endDate`, `year`, and `displayName`, plus per-team `stats[]` arrays. The
two detection signals:

### Offseason

`standings.season.startDate > today` (in UTC) → the standings response is
showing the most recently completed season's records, and the next season
has not yet started. Confirmed live for NFL: in May 2026, NFL standings'
`season.startDate` is `"2026-08-06"`.

For leagues currently mid-season, `season.startDate` is in the past.

### Postseason

At least one entry in `standings.children[*].standings.entries[*].stats`
has a stat with `name == "clincher"` and `displayValue == "e"`. The
presence of an eliminated team means the regular season is over and
postseason is underway. Confirmed live for NHL: 16 of 32 teams have
`clincher = "e"` right now.

If `clincher == "e"` is absent everywhere but other clinch values
(`x`/`y`/`z`) are present, we are still in regular season with some teams
having clinched. No postseason prefix in that case; per-team qualified
annotations are also skipped to keep regular-season output stable.

### Regular season

Neither of the above triggers. Output is unchanged from current behavior.

## Output formats

### Phase prefix

| Phase           | Prefix                                                    |
| --------------- | --------------------------------------------------------- |
| Regular season  | none                                                      |
| Postseason      | `"The NHL is in the playoffs. "`                          |
| Offseason       | `"The NFL is in the offseason. Last season. "`            |

The prefix uses the resolved league name (`info.name`) — same source as
the existing `unknown_league_message` and other tools.

### Per-team annotation

Only emitted when:

- The league's standings entries carry a `clincher` stat for at least one
  team (i.e., the league instruments playoff qualification at all), AND
- The league is past regular season (postseason or offseason phase).

Then per row:

| `clincher.displayValue` | Annotation                              |
| ----------------------- | --------------------------------------- |
| `"x"`, `"y"`, `"z"`     | `", qualified for the playoffs"`        |
| `"e"`                   | `", did not qualify for the playoffs"`  |
| anything else, missing  | no annotation                           |

The annotation appears appended to the existing per-row sentence:

- Before: `"Boston Celtics first at 52 wins and 18 losses."`
- After (qualified): `"Boston Celtics first at 52 wins and 18 losses, qualified for the playoffs."`
- After (eliminated): `"New Jersey Devils thirteenth at 42 wins and 37 losses, did not qualify for the playoffs."`

The TTS-safety rules already enforced by `format.py` continue to apply.
"qualified for the playoffs" and "did not qualify for the playoffs" are
both clean prose with no parens, slashes, ampersands, or abbreviations.

### Combined examples

NFL in offseason (May 2026):
> `"The NFL is in the offseason. Last season. AFC East. Buffalo Bills first at 12 wins and 5 losses, qualified for the playoffs. Miami Dolphins second at 9 wins and 8 losses, did not qualify for the playoffs. ..."`

NHL in postseason (May 2026):
> `"The NHL is in the playoffs. Eastern Conference. Carolina Hurricanes first at 53 wins and 20 losses, qualified for the playoffs. ... New Jersey Devils thirteenth at 42 wins and 37 losses, did not qualify for the playoffs."`

NBA mid regular season:
> `"Eastern Conference. Boston Celtics first at 52 wins and 18 losses. ..."` (unchanged)

EPL during its season (no clinch instrumentation):
> unchanged from today.

EPL between seasons (June–July, when `startDate` is in the future):
> `"The Premier League is in the offseason. Last season. Premier League. Arsenal first at 25 wins and 5 losses. ..."` (offseason prefix only, no per-team annotation)

## Code organization

### `sports_mcp/format.py`

- `standings_block(label, rows)` is extended. Each row dict gains an
  optional `qualification` key with values `"qualified"`, `"eliminated"`,
  or absent. When present, the corresponding annotation phrase is
  appended to that row's sentence. Rows with no `qualification` key
  render exactly as today (regression guard).
- New helper `season_phase_prefix(league_name: str, phase: str) -> str`
  takes the resolved league name and a phase string (`"postseason"` or
  `"offseason"`). Returns the prefix sentence (with trailing space) or
  empty string for `"regular"` / unknown.

### `sports_mcp/tools.py`

`get_standings` is modified:

1. After fetching the standings response, derive the league phase via two
   helpers (private to `tools.py`):
   - `_detect_offseason(data: dict) -> bool` — checks
     `data["season"]["startDate"]` against UTC today.
   - `_detect_postseason(data: dict) -> bool` — scans
     `children[*].standings.entries[*].stats` for any `clincher == "e"`.
2. Compute `phase` as `"offseason"` if offseason, else `"postseason"` if
   postseason, else `"regular"`.
3. When building each row dict in `_rows_from_standings_entries`, add a
   `qualification` key if and only if `phase != "regular"` AND the entry
   has a `clincher` stat. The value is `"qualified"` for `x`/`y`/`z`,
   `"eliminated"` for `e`, otherwise omitted.
4. Build the standings blocks as today.
5. Prepend `season_phase_prefix(info.name, phase)` to the joined output.

### Helper extraction

`_rows_from_standings_entries` currently lives in `tools.py` and produces
`{"name", "wins", "losses"}` dicts. It will be extended to optionally take
the phase and emit the `qualification` key. No public-API impact.

## Testing

### `tests/test_format.py`

Three new format tests covering the row annotation:

- `test_standings_block_with_qualified_annotation` — row dict includes
  `qualification="qualified"`. Output ends with
  `"...52 wins and 18 losses, qualified for the playoffs."`.
- `test_standings_block_with_eliminated_annotation` — row dict includes
  `qualification="eliminated"`. Output ends with
  `"...42 wins and 37 losses, did not qualify for the playoffs."`.
- `test_standings_block_no_qualification_unchanged` — row dict has no
  `qualification` key. Output matches the current shape exactly. This is
  the regression guard.

Three new format tests for `season_phase_prefix`:

- `test_season_phase_prefix_offseason` → `"The NFL is in the offseason. Last season. "`
- `test_season_phase_prefix_postseason` → `"The NHL is in the playoffs. "`
- `test_season_phase_prefix_regular_returns_empty` → `""`

All assert TTS safety via `no_punctuation_artifacts`.

### `tests/test_tools.py`

Four new integration tests:

- `test_get_standings_offseason_nfl` — fixture payload with `season.startDate`
  set to a future date. Output starts with
  `"The NFL is in the offseason. Last season."`.
- `test_get_standings_postseason_nhl` — fixture payload with one team
  having `clincher.displayValue == "e"`. Output starts with
  `"The NHL is in the playoffs."` and includes both annotations.
- `test_get_standings_regular_season_unchanged` — fixture with no clinch
  data and `season.startDate` in the past. Output is exactly the
  pre-change format (regression guard).
- `test_get_standings_postseason_no_clinch_data` — fixture for a league
  past its regular season but without a `clincher` stat in the entries.
  Output gets the postseason prefix but no per-team annotations.

The existing `test_get_standings_two_conferences` and
`test_get_standings_single_table` tests have payloads without clinch
data and without future `startDate`, so they continue to pass. They are
not modified.

## Risks

- **`clincher == "*"` (and other unexpected codes).** The live NHL
  response shows one team with `clincher = "*"` (the league's top team
  during postseason). The rule says: anything not in `{x, y, z, e}` →
  no annotation. That team's row reads as a regular-season row, which
  is acceptable for v1. If this proves noisy in practice we can extend.
- **Soccer competitions with no `clincher` stat.** EPL standings have no
  clinch column; rule already handles this (no annotation). UCL and
  World Cup are similar. The only signal that could fire for these is
  the offseason prefix when their season window has ended; that is the
  intended behavior.
- **Heuristic vs. ESPN reality.** ESPN's `season.type.id` proved
  unreliable for NFL offseason detection (probed live: NFL still reports
  `type.id == "2"` during offseason). The startDate-vs-today rule is the
  fallback. If ESPN changes its standings response shape, the rules may
  need adjustment; the smoke script (`scripts/smoke.py`) and the format
  tests give us a check.
