# chess-results-api

An experimental Python 3.12+ decoder for Swiss-Manager tournament files, with no
runtime dependencies. Supports individual Swiss (TUNX), individual round-robin
(TURX), team round-robin (TUTX), and team Swiss (TUMX).

## Setup

Use [uv](https://docs.astral.sh/uv/getting-started/installation/) to create `.venv`
and install the package and development tools:

```sh
uv sync --locked
```

## Usage

```python
from chess_results_api import load_tournament

tournament = load_tournament("tests/fixtures/olympiad2026open_1469895.TUMX")
print(tournament.metadata.name, tournament.tournament_type.name)
for round_ in tournament.rounds:
    for game in round_.games:
        print(game.white_player, game.black_player, game.result, game.points)
```

`load_tournament(path)` and `decode_tournament(data: bytes)` detect the format from
its contents and return frozen, typed records for metadata, players, teams,
rounds, pairings, and scores. Detected malformed or unsupported layouts raise
`SwissManagerDecodeError`; filesystem errors propagate unchanged.

The decoder uses standard 1 / ½ / 0 scoring. Unknown results remain unscored, and
unidentified data is preserved. It does not calculate rankings or tie-breaks.
Player and team references are one-based, with special values for empty slots,
byes, and unpaired entries. See the [format notes](docs/swiss-manager-format.md)
for these conventions, observed layouts, and validation limits.

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Local binaries and reference snapshots belong in `tests/fixtures/`, which is
ignored by Git and excluded from distributions. Tests requiring missing fixtures
skip; synthetic tests run offline without them. `uv build` creates distribution
archives in `dist/` for a future PyPI release.

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit and branch conventions, and
[citations.cff](citations.cff) for citation metadata.
