# chess-results-api

A Python 3.12+ package for reading Chess-Results tournament data. The first module
is an experimental Swiss-Manager TUMX decoder, with no runtime dependencies.

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
```

`decode_tumx(data: bytes)` accepts in-memory data. Both entry points return frozen,
typed records and raise `TumxDecodeError` for detected malformed or unsupported
layouts. Filesystem errors from `load_tumx` propagate unchanged.

Swiss-Manager identifies `.TUMx` as its team Swiss-system tournament format in its
[manual](https://swiss-manager.at/unload/SwissManagerHelp_ENG.pdf). The binary layout
here was inferred from the supplied 2026 Open Olympiad file, not from a published
binary specification. Support is currently limited to that observed layout:

- Tournament text and ID, player names, titles, federations, ratings and FIDE IDs.
- Teams, captains, and players' one-based team and board numbers.
- Exact raw sections, including unparsed configuration, schedule, pairings and
  results. Concatenating `section.data` in order reproduces the original file.

Record order is not a ranking. Zero ratings and FIDE IDs remain zero. Pairing and
score interpretation, other Swiss-Manager layouts, and an HTTP client are future
work; structural validation cannot establish compatibility with every TUMX file.

## Local fixtures

`tests/fixtures/` is ignored by Git and excluded from distribution archives.
Keep `olympiad2026open_1469895.TUMX` there to run the local regression test against
1,025 players and 206 teams. Without it, only that test is skipped; synthetic
tests still exercise decoding, Unicode, invalid offsets and truncated records.
