# Swiss-Manager format notes

These layouts were inferred from local fixtures and checked against published
results; they are not a complete vendor specification. The
[Swiss-Manager manual](https://swiss-manager.at/unload/SwissManagerHelp_ENG.pdf)
identifies the extensions. Unknown fields remain accessible as raw data, and
concatenating `section.data` in order reproduces the input byte for byte.

## Binary layout

Integers are little-endian. Strings have a `uint16` UTF-16 code-unit count followed
by UTF-16LE text. Section markers are a tag byte followed by `ff 89 44`.

| Section | Tag | Record structure |
| --- | --- | --- |
| Header | `93` | 108 fixed bytes, then 132 strings; tournament ID at byte 32 |
| Configuration | `95` | Type, counts, dates, tie-break codes, and opaque settings |
| Schedule | `a3` | Per round: 16 strings + 76 numeric bytes |
| Players | `a5` | Per player: 18 strings + 134 numeric bytes |
| Games | `b3` | Per game: two `uint16` references, result byte, 16 opaque bytes |
| Teams | `b5` | Per team: five strings + 96 numeric bytes |
| Team matches | `c3` | Per match: two `uint16` references, two `uint16` scores, seven opaque bytes |
| Directory / end | `d3` / `e3` | 36 bytes: directory marker, seven `uint32` values, end marker |

Configuration offset 15 (`uint16`, relative to its marker) determines the format;
filenames are not used for detection:

| Value | Extension | Format | Team sections |
| ---: | --- | --- | --- |
| 0 | TUNX | Individual Swiss | Absent |
| 1 | TURX | Individual round-robin | Absent |
| 2 | TUTX | Team round-robin | Present |
| 3 | TUMX | Team Swiss | Present |

The directory stores offsets for schedule, players, games, optional teams and
matches, then itself; unused entries are zero. Boundaries are read from these
offsets, not found by scanning for markers.

Configuration offset **27** holds the scheduled round count; offset 21 must not
be used to truncate the schedule. Each round's numeric block holds its date at
0 (`uint32`) and game/match counts at 6/8 (`uint16`). These counts delimit pairing
records; scheduled rounds need not be paired or completed.

## References, results, and missing values

- Player/team references are one-based file positions, not rankings. Player `0`
  is an empty slot. Second-team or individual black-player values `ffff` and
  `fffe` become `-1` (bye) and `-2` (not paired); never use them as tuple indices.
- Individual events have empty `teams` and round `matches`, and
  `match_number=None`. Normal games use round-local pairing positions as board
  numbers; special entries have `board_number=None`.
- Dates use YYYYMMDD. Zero dates become `None`; partial birth dates preserve
  unknown components, so `19920000` is a year alone. Round times remain local
  strings without an inferred timezone. Zero ratings and FIDE IDs remain zero.
- Player board numbers are roster positions; game board numbers refer to that
  round. Stored pairing counts include byes, exclusions, and empty slots.

| Result code | Meaning | White / black points |
| ---: | --- | --- |
| 0 | Unreported | `None` |
| 1 / 4 | White win / win by forfeit | 1 / 0 |
| 2 | Draw | ½ / ½ |
| 3 / 5 | Black win / win by forfeit | 0 / 1 |
| 6 | Double forfeit | 0 / 0 |
| 9 | Individual bye | 1 / `None` |
| 10 | Double zero | 0 / 0 |

Codes 1–6 match the [user guide, page 12](https://swiss-manager.at/unload/swiss_manager_user_guide.pdf).
Unknown codes remain unscored. Special individual entries have no opponent score:
code 3 gives `(0.0, None)`, code 2 gives `(0.5, None)`, and code 0 gives
`points=None`. Code 9 with an ordinary opponent remains unscored.

Code 10 is distinct from double forfeit: the 2024 Women's Olympiad
[round 7, board 60.4](https://chess-results.com/tnr967172.aspx?lan=1&art=3&rd=7)
shows Takayasu–Aayat as 0–0; Pakistan–Japan totals `(1.0, 2.0)` in file order.
The [reported TUMX evidence](https://github.com/zyf0717/chess-results-api/issues/3)
records its code and checksum. `played` recognizes only codes 1–3 with both players
present; code 10 remains excluded without implying a forfeit.

TUTX assigns a fixed block of `boards_per_match` games to each match. Empty
`(white=0, black=0, result=0)` slots are retained and unscored. TUMX links games
through player team membership, using the known opponent when one player is
missing. Ordinary match totals sum board scores; incomplete totals are `None`.
Special team entries use stored scores at match offsets 4 and 6, in half-point
units, rather than assuming a win or loss.
