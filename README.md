# chess-results-api

[![CI](https://github.com/zyf0717/chess-results-api/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/zyf0717/chess-results-api/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/zyf0717/chess-results-api/blob/main/pyproject.toml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](https://github.com/zyf0717/chess-results-api/blob/main/LICENSE)

An experimental Python 3.12+ package for downloading Chess-Results tournament
files and decoding Swiss-Manager data. Supports individual Swiss (TUNX), individual
round-robin (TURX), team round-robin (TUTX), and team Swiss (TUMX).
Local decoding has no runtime dependencies; downloading uses optional Playwright.

## Installation

After v0.1.0 is published, install into a virtual environment using
[uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv venv --python 3.12
uv pip install chess-results-api
```

## Usage

```python
from chess_results_api import load_tournament

tournament = load_tournament("tournament.TUMX")
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
byes, and unpaired entries. See the
[format notes](https://github.com/zyf0717/chess-results-api/blob/main/docs/swiss-manager-format.md)
for these conventions, observed layouts, and validation limits.

## Download a tournament

Install the browser extra and Chromium once:

```sh
uv pip install "chess-results-api[browser]"
uv run --no-project playwright install chromium
```

```python
from chess_results_api import download_tournament, load_tournament

path = download_tournament(1502346, "tournament.TUNX")
tournament = load_tournament(path)
```

The downloader opens the details form and follows the file link in an isolated
browser session, blocking images, fonts, and media to reduce page traffic.
It validates the binary and tournament ID before writing the
destination, replacing an existing file. The parent directory must exist.
Browser failures or unavailable downloads raise `TournamentDownloadError`;
unsupported binaries raise `SwissManagerDecodeError`. Options include
`timeout=30` (seconds per browser operation) and `headless=False`.

## Development

From a repository checkout:

```sh
uv sync --locked --extra browser
uv run playwright install chromium
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Local binaries and reference snapshots belong in `tests/fixtures/`, which is
ignored by Git and excluded from distributions. Tests requiring missing fixtures
skip; synthetic tests run offline without them. `uv build` creates distribution
archives in `dist/`. Before publication, these wheels can be installed with
`uv pip install dist/chess_results_api-0.1.0-py3-none-any.whl`.
Browser tests use intercepted requests and skip when Playwright or Chromium is absent.

See [CONTRIBUTING.md](https://github.com/zyf0717/chess-results-api/blob/main/CONTRIBUTING.md)
for commit and branch conventions,
[CHANGELOG.md](https://github.com/zyf0717/chess-results-api/blob/main/CHANGELOG.md)
for release notes, and
[citations.cff](https://github.com/zyf0717/chess-results-api/blob/main/citations.cff)
for citation metadata.
