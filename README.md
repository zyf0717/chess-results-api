# chess-results-api

A Python 3.12+ package for reading Chess-Results tournament data. The experimental
Swiss-Manager binary decoder has no runtime dependencies and supports:

| Extension | Tournament format |
| --- | --- |
| TUNX | Individual Swiss |
| TURX | Individual round-robin |
| TUTX | Team round-robin |
| TUMX | Team Swiss |

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

## Read a tournament file

```python
from chess_results_api import load_tournament

tournament = load_tournament("tests/fixtures/olympiad2026open_1469895.TUMX")
print(tournament.metadata.name, tournament.tournament_type.name)
for player in tournament.players:
    print(player.number, player.first_name, player.last_name, player.rating)

for round_ in tournament.rounds:
    print(round_.number, round_.scheduled_date, round_.start_time)
    for match in round_.matches:
        print(match.first_team, match.second_team, match.board_points)
    for game in round_.games:
        print(game.board_number, game.white_player, game.black_player, game.result, game.points)
```

`decode_tournament(data: bytes)` accepts in-memory data. Both entry points detect
the tournament type from its contents, return shared frozen typed records, and
raise `SwissManagerDecodeError` for detected malformed or unsupported layouts.
Filesystem errors from `load_tournament` propagate unchanged. Shared types live
in `chess_results_api.models`.

The extension meanings follow the
[Swiss-Manager manual](https://swiss-manager.at/unload/SwissManagerHelp_ENG.pdf).
Binary layouts were inferred from the supplied files, not from a published binary
specification. Decoded data includes:

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
`0` is an empty slot; a second-team or individual black-player reference of `-1`
is a bye, and `-2` is not paired. Never index a tuple with those sentinels.
Individual events have empty `teams` and `round_.matches` tuples and a game
`match_number` of `None`. A special individual entry also has `board_number=None`
and no opponent score: a reported bye yields `points=(1.0, None)`. Future-round
exclusions with no result retain `points=None`. A player's `board_number` is
their roster position; a game's `board_number` is their playing board that round.
Round times are local strings, without an inferred timezone. Birth year alone is
represented as `PartialDate(year, None, None)`, not January 1.

Record order is not a ranking. Zero ratings and FIDE IDs remain zero. Application
settings whose meanings are still unidentified are preserved in `raw_data` or
`numeric_data`. Official standings and tie-break values require separate
calculations; this decoder does not infer them from record order. Other TUMX
layouts and alternative scoring rules need additional fixtures and verification.
See [the shared format notes](docs/swiss-manager-format.md) and
[the TUMX offset notes](docs/tumx-format.md) for evidence and limits.

## Local fixtures

`tests/fixtures/` is ignored by Git and excluded from distribution archives.
Keep the supplied binaries there to run local regressions for all four formats;
the exact filenames are listed in the format notes. The optional
`standings-reference.html`, `tunx-reference.html`, `turx-reference.html`, and
`tutx-reference.html` snapshots check player or team totals independently against
published standings. Missing local inputs skip their respective tests. Synthetic
tests run offline and cover each format, Unicode, malformed records, missing data,
results, sentinels, partial dates, and empty future-round board slots.
