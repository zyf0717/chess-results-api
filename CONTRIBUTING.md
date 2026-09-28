# Contributing

## Development

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked --extra browser
uv run playwright install chromium
```

This creates `.venv` with the package, pytest, Ruff, and Playwright. For decoder
work only, omit `--extra browser` and the Chromium installation. Update
`pyproject.toml` and `uv.lock` together when changing dependencies.

Before opening a PR:

```sh
uv run ruff format .
uv run ruff check .
uv run pytest
uv build
```

CI runs on pull requests and pushes to `main`: Ubuntu Python 3.12–3.14, Windows
3.12, and macOS 3.12. Describe the change and its validation in the PR.

## Commits and branches

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
for commits and squash-merge PR titles:

```text
<type>[optional scope][!]: <description>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore`, or `revert`. Use an imperative description. Mark breaking changes with
`!` and explain the migration in a `BREAKING CHANGE:` footer.

Branch names use `<type>/<short-description>` with lowercase, hyphen-separated
words, such as `feat/tournament-download` or `fix/empty-player-slots`.

## Code and tests

Keep changes focused, readable, and typed. Prefer small functions and explicit
data flow. Document decoder evidence in the [format notes](docs/swiss-manager-format.md),
preserve unidentified bytes, and check boundaries, references, missing values,
dates, and score units. Add regression or edge-case tests for behavior changes.

Tests must run offline; browser tests intercept requests. Keep local binaries and
reference snapshots in `tests/fixtures/`, which is ignored by Git and excluded
from distributions. Never force-add fixtures. Tests requiring missing fixtures
or browser installations skip; use synthetic data for portable coverage.

## Releasing

1. Prepare `release/v<version>` with matching versions in `pyproject.toml` and
   `citations.cff`, dated release notes in `CHANGELOG.md`, and updated README text.
2. Merge the preparation PR into `main` and confirm CI passes.
3. Tag the release commit on `main` and push that tag:

   ```sh
   git switch main
   git pull --ff-only
   git tag -a v0.1.1 -m "Release v0.1.1"
   git push origin v0.1.1
   ```

The [Publish workflow](.github/workflows/publish.yml) runs on `v*` tag pushes.
It verifies that the tagged commit belongs to `main` and the tag matches the
package version, builds and tests the wheel, then publishes the same artifacts
to TestPyPI followed by PyPI. Publishing uses the existing Trusted Publishers
and GitHub environments. Creating a GitHub release does not trigger publishing.

Published versions are immutable. For a partial workflow failure, rerun failed
jobs; use a new version for changed distributions rather than moving a release tag.
