# Changelog

## 0.1.1 — 2026-09-28

- Score result code 10 as a distinct double zero, including team totals.
- Add validated `download_tournament_bytes` and structured download error details.

## 0.1.0 — 2026-09-28

Initial release for Python 3.12+.

- Decode Swiss-Manager TUNX, TURX, TUTX, and TUMX files through
  `load_tournament` and `decode_tournament`.
- Read tournament metadata, players, teams, schedules, pairings, results, and
  team board scores as typed records, preserving unknown fields and source bytes.
- Download files with `download_tournament` using optional Playwright/Chromium,
  isolated sessions, tournament-ID validation, and reduced page traffic.
- Support local decoding without runtime dependencies. Distribute the `py.typed`
  marker for type checkers.

The decoder is experimental and covers observed binary layouts. Scoring assumes
1 / ½ / 0; official rankings and tie-breaks are not calculated. Downloading depends
on the Chess-Results website and requires a separate Chromium installation.
Local tournament binaries and reference snapshots are excluded from distributions.
