# Observed TUMX layout

This describes `olympiad2026open_1469895.TUMX` (398,846 bytes), SHA-256
`57266aac705e5a233e2bd8f21b2d174f052662075e1727b9084fb8ab350503a1`.
It is reverse-engineering evidence for one layout, not a complete Swiss-Manager
binary specification. Unidentified bytes remain accessible without invented names.
See [the shared format notes](swiss-manager-format.md) for the other formats and
the evidence that corrected the header-string and round-count interpretations.

All integers are little-endian. A string is a `uint16` UTF-16 code-unit count
followed by that many UTF-16LE code units. Non-BMP characters consume two units.
Record offsets below include section markers unless stated otherwise.

## Sections and directory

Each marker consists of a tag byte followed by `ff 89 44`.

| Section | Tag | Absolute offset | Length including marker |
| --- | --- | ---: | ---: |
| Header | `93` | 0 | 1268 |
| Configuration | `95` | 1268 | 5887 |
| Schedule | `a3` | 7155 | 1302 |
| Players | `a5` | 8457 | 240998 |
| Board pairings | `b3` | 249455 | 94840 |
| Teams | `b5` | 344295 | 37456 |
| Team pairings | `c3` | 381751 | 17059 |
| Directory and end marker | `d3`, `e3` | 398810 | 36 |

The final 36 bytes are the directory marker, seven `uint32` values, and the end
marker. Values 0–4 point to schedule, players, board pairings, teams, and team
pairings; value 5 points back to the directory; value 6 is zero. This gives checked
section boundaries without searching for marker-like bytes inside arbitrary data.

The header starts with 108 fixed bytes, including the tournament ID (`uint32` at
32), followed by 132 strings before configuration. In this fixture the last 106
strings are empty, accounting for 212 bytes previously treated as padding. Known
string indices are name 0, section 1, remarks 2, organizer 4, location 5, time
control 14, federation 20, chief arbiter 21, and website 24. All strings are exposed.
The remaining header fields are retained in `Tournament.sections`.

## Configuration

Offsets are relative to the `95` marker.

| Offset | Type | Decoded field | Fixture value |
| ---: | --- | --- | --- |
| 15 | uint16 | Tournament type (team Swiss) | 3 |
| 23 | uint16 | Player count | 1025 |
| 27 | uint16 | Scheduled round count | 11 |
| 31 | uint16 | Number of selected tie-breaks | 4 |
| 33 | uint16 array | Selected tie-break codes | 13, 74, 1, 75 |
| 51 | uint16 | Team count | 206 |
| 53 | uint16 | Playing boards per match | 4 |
| 75 | uint32 | Start date, YYYYMMDD | 20260916 |
| 79 | uint32 | End date, YYYYMMDD | 20260927 |
| 1275 | uint32 | FIDE event ID | 492113 |

Nine tie-break slots fit before the team count. The published list identifies the
four selected algorithms as match points, Olympiad Sonneborn–Berger with one cut,
board points, and adjusted opponent match points with one cut. The decoder exposes
codes; it does not implement these algorithms or interpret their option bytes.
Other configuration flags, numeric values, an ASCII UUID-shaped value, and unused
space are retained in `Configuration.raw_data`.

## Players and teams

Each player has 18 string fields followed by a 134-byte fixed block. Known strings
are last name 0, first name 1, display name 3, title 4, federation 10, and category
11. Indices 2 and 17 also contain text in this fixture; their semantics are not
assigned. All 18 are exposed in `text_fields`.

| Offset in fixed block | Type | Field |
| ---: | --- | --- |
| 30 | uint16 | Recorded sex code (0/1 observed; no inferred identity) |
| 32 | uint16 | Rating |
| 38 | uint32 | Birth date, YYYYMMDD with zero unknown components |
| 48 | uint32 | FIDE ID |
| 52 | uint16 | One-based team record number |
| 54 | uint16 | Roster board number |

`19920000` means birth year 1992, not a full date. Zero means no date. Names retain
original spelling and whitespace. Other nonzero fields at 46, 76, and 80, and all
remaining bytes, are retained in `Player.numeric_data`; they are not assumed to
be ranks, starting numbers, or scores.

Each team has five strings (name, display name, captain, federation, group) and a
96-byte fixed block. The complete block is exposed as `Team.numeric_data`. Values
at 42 and 44 are nonzero in this fixture but their purposes remain unidentified.

## Schedule and board results

Each schedule entry consists of 16 strings and 76 fixed bytes. String 0 is the
local start-time text; the other strings are empty in the fixture. Fixed offsets
0, 6, and 8 hold the `uint32` YYYYMMDD date, `uint16` board-game count, and `uint16`
team-pairing count respectively. All other bytes remain exposed as `numeric_data`.
The schedule supplies the number of records to consume from each pairing section
for each round; no round separator or fixed number of pairings is assumed.

| Rounds | Board games per round | Team pairing entries per round |
| --- | ---: | ---: |
| 1 | 404 | 105 |
| 2–3 | 408 | 104 |
| 4–11 | 412 | 103 |

The 11 rounds run September 16–27, with September 22 omitted. The final round
starts at 11:00; the others start at 15:00. No timezone is encoded or inferred.

Each board game is 21 bytes: two `uint16` player record numbers, a result byte,
and 16 uninterpreted bytes (all zero in this fixture). Player 0 is an empty slot.
The reference numbers are file positions, not the values at player-block offset 46.

| Result byte | Meaning | White / black board points |
| ---: | --- | --- |
| 0 | Unreported | Unknown |
| 1 | White win | 1 / 0 |
| 2 | Draw | ½ / ½ |
| 3 | Black win | 0 / 1 |
| 4 | White wins by forfeit | 1 / 0 |
| 5 | Black wins by forfeit | 0 / 1 |
| 6 | Double forfeit | 0 / 0 |

The [Swiss-Manager user guide, page 12](https://swiss-manager.at/unload/swiss_manager_user_guide.pdf)
documents the same result-entry codes 1–6. Their use in these binary records is
an inference validated against the published tournament scores. Unrecognized
codes are retained with `result=None` and `points=None`. Code 0 is covered
synthetically; all 4,516 fixture records have reported results. Standard board
scoring is used; alternative scoring rules are not inferred from opaque settings.

## Team pairings and score reconstruction

Each team pairing is 15 bytes. Offsets 0 and 2 hold two `uint16` team references.
Second references `ffff` and `fffe` are exposed as -1 (bye) and -2 (not paired),
matching the published pairing table. Offsets 4 and 6 hold stored board scores
in half-point units. Those values are zero for ordinary matches in this fixture;
Kiribati's round-3 bye stores 4, which the published table shows as two board points.
Bytes 8–14 remain uninterpreted (byte 8 is 1 in two matches).

Ordinary match scores are derived by linking games through players' team numbers
and adding each side's actual board scores. The first team is not always white
on every board. A missing player is associated using the known opponent's team,
so the two empty Liechtenstein slots in round 10 still give El Salvador its
correct 4–0 result. Playing board numbers follow the games' order within the
match; they differ from roster positions when a reserve plays.

There are 1,129 ordinary matches, seven not-paired entries, and one bye. Each
ordinary match has four games. Unknown game scores or fewer than the configured
number of boards produce an unknown match total. Special entries use their stored
scores; they are not automatically treated as wins or losses.

## Verification and remaining limits

The reference file is checked structurally, including participant counts, round
boundaries, complete consumption of pairing sections, valid references, unique
players/teams within a round, and game-to-match consistency. Synthetic tests cover
malformed inputs and cases not present in the reference, including unknown scores.
Raw sections reconstruct all 398,846 input bytes exactly.

Independent references retrieved September 28, 2026:

- [Final standings](https://chess-results.com/tnr1469895.aspx?lan=1&art=0&zeilen=99999):
  all 206 reconstructed team board-point totals agree exactly, including
  Uzbekistan 32½, USA 29, India 28½, Kiribati 16½ and Marshall Islands 1½.
- [Round-3 team pairings](https://chess-results.com/tnr1469895.aspx?lan=1&art=2&rd=3):
  confirms the bye and not-paired sentinel meanings and the bye's stored score.
- [Kiribati's results](https://chess-results.com/tnr1469895.aspx?lan=1&art=20&snr=205):
  cross-checks ordinary results and forfeits.

These references are optional local HTML fixtures, not runtime network dependencies.
Their contents are excluded from Git and package archives. This reader decodes
the tournament records throughout the supplied file, but full semantic decoding
of every Swiss-Manager application setting still requires additional evidence.
It does not calculate official rankings, match points, tie-breaks, performance
ratings, rating changes, or norms; these are derived quantities, not identified
stored results in this layout. Other file versions require separate validation.
