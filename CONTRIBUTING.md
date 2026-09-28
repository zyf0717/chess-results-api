# Contributing

## Development setup

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --locked
```

This creates `.venv` and installs the package, pytest, and Ruff. Use `uv run` for
project commands. When changing dependencies, update `pyproject.toml` and `uv.lock`
together.

## Commit messages

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>[optional scope][!]: <description>
```

Use `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore`, or `revert`. Write a concise description in the imperative. Mark breaking
changes with `!` and explain the migration in a `BREAKING CHANGE:` footer.

Examples:

```text
feat(tumx): decode round schedules
fix(tumx): preserve empty player slots
docs: document the contribution workflow
```

## Branch names

Work on a branch named with a Conventional Commit type followed by `/` and a
short lowercase, hyphen-separated description:

```text
<type>/<short-description>
```

Use the same types as commit messages. Examples: `feat/tumx-round-schedules`,
`fix/empty-player-slots`, and `docs/contributing-guide`. Do not include spaces,
colons, or the breaking-change `!` marker in branch names.

## Changes and verification

Keep changes focused, readable, and typed. Prefer small functions and explicit
data flow. For decoder changes, document the binary-layout evidence in
[`docs/tumx-format.md`](docs/tumx-format.md), preserve unidentified data, and check
record boundaries, missing values, reference numbers, dates, and score units.

Add regression or edge-case tests when changing behavior. Tests must run offline.
Keep local source files and downloaded reference snapshots in `tests/fixtures/`;
that directory is ignored by Git and excluded from package archives. Do not
force-add fixtures. Use synthetic inputs for tests that must run in every checkout.

Before submitting a pull request, run:

```sh
uv run ruff format .
uv run ruff check .
uv run pytest
uv build
```

Tests requiring optional local fixtures may skip when those files are absent.
Describe the behavior changed, the supporting evidence, and the checks run in
the pull request. Use a Conventional Commit title for squash merges.
