# chess-results-api

A Python 3.12+ package for reading Chess-Results tournament data. The first module
is an experimental Swiss-Manager TUMX decoder, with no runtime dependencies.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and required
commit and branch naming conventions, and [citations.cff](citations.cff) for citation metadata.

## Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

`uv sync` creates the project's `.venv` and installs the package in editable mode
along with pytest and Ruff. `uv run` uses that environment automatically; optional
shell activation is `source .venv/bin/activate`. The development interpreter is
pinned to Python 3.12 in `.python-version`; the package supports Python 3.12+.
Commit `uv.lock` to keep development dependencies reproducible.

The package uses a `src/` layout. `uv build` produces a wheel and source archive
in `dist/` for a future PyPI release; it does not publish them.

## Read a TUMX file

```python
from chess_results_api.tumx import load_tumx

tournament = load_tumx("tests/fixtures/olympiad2026open_1469895.TUMX")
print(tournament.metadata.name)
for player in tournament.players:
    team = tournament.teams[player.team_number - 1]
    print(player.first_name, player.last_name, player.rating, team.name)

for round_ in tournament.rounds:
    print(round_.number, round_.scheduled_date, round_.start_time)
    for match in round_.matches:
        print(match.first_team, match.second_team, match.board_points)
        for game in match.games:
            print(game.board_number, game.white_player, game.black_player, game.result)
```

`decode_tumx(data: bytes)` accepts in-memory data. Both entry points return frozen,
typed records and raise `TumxDecodeError` for detected malformed or unsupported
layouts. Filesystem errors from `load_tumx` propagate unchanged.

Swiss-Manager identifies `.TUMx` as its team Swiss-system tournament format in its
[manual](https://swiss-manager.at/unload/SwissManagerHelp_ENG.pdf). The binary layout
here was inferred from the supplied 2026 Open Olympiad file, not from a published
binary specification. Support is currently limited to that observed layout:

- Tournament metadata, dates, participant/round counts, FIDE event ID, board count,
  and configured tie-break codes.
- Players, ratings, FIDE IDs, partial birth dates, categories, recorded sex codes,
  teams, captains, groups, and roster positions.
- Every scheduled round, board pairing, result, and team match, including forfeits,
  byes, unpaired teams, and empty player slots.
- Board scores and per-match totals under standard 1 / ½ / 0 scoring. Half-points
  are exactly representable by the returned Python floats. Unreported or unknown
  game results and incomplete matches have `None` scores.
- All decoded text fields and original numeric record data. Concatenating
  `section.data` in order reproduces the original file byte for byte.

Player and team references are one-based file positions. A player reference of
`0` is an empty slot; a second-team reference of `-1` is a bye, and `-2` is not
paired. Never index a tuple with those sentinels. A player's `board_number` is
their roster position; a game's `board_number` is their playing board that round.
Round times are local strings, without an inferred timezone. Birth year alone is
represented as `PartialDate(year, None, None)`, not January 1.

Record order is not a ranking. Zero ratings and FIDE IDs remain zero. Application
settings whose meanings are still unidentified are preserved in `raw_data` or
`numeric_data`. Official standings and tie-break values require separate
calculations; this decoder does not infer them from record order. Other TUMX
layouts and alternative scoring rules need additional fixtures and verification.
See [the binary layout notes](docs/tumx-format.md) for offsets, evidence, and limits.

## Local fixtures

`tests/fixtures/` is ignored by Git and excluded from distribution archives.
Keep `olympiad2026open_1469895.TUMX` there to run the local regression test against
1,025 players, 206 teams, 11 rounds, 4,516 board games, and 1,137 team pairings.
The optional `standings-reference.html` snapshot from the published final standings
checks all 206 teams' board-point totals independently. Missing local inputs skip
their respective tests. Synthetic tests run offline and cover Unicode, malformed
records, missing data, all observed results, sentinels, and partial dates.
