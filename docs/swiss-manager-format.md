# Shared Swiss-Manager binary formats

The public `load_tournament` and `decode_tournament` functions share one reader
for TUNX, TURX, TUTX and TUMX. `models.py` contains common records; `_binary.py`
contains bounded reads, date decoding, and the shared exception. All four formats
use the shared API directly.

These are observed layouts, not a complete vendor specification. The
[Swiss-Manager manual](https://swiss-manager.at/unload/SwissManagerHelp_ENG.pdf)
identifies the four extensions; the binary details below come from local files
and comparisons with published results. Unidentified data is preserved verbatim.

## Common layout and corrections

The marker bytes, UTF-16LE strings, numeric endianness, participant records, and
schedule fields described in [the TUMX notes](tumx-format.md) are shared across
all four observed types. The expanded fixture set establishes two corrections:

- After the 108-byte fixed header there are **132 length-prefixed strings**.
  The Olympiad file's last 106 empty strings previously looked like 212 bytes of
  padding. Abu Dhabi has additional arbiter text at string index 35. Skipping
  fixed padding would misalign its configuration record.
- Configuration offset **27** is the scheduled round count. Offset 21 can differ:
  Abu Dhabi has seven scheduled rounds and the value six at offset 21. That
  second value is not used to limit schedule decoding or classify completed games.

Configuration offset 15 contains the tournament type:

| Value | Enum | Extension | Team sections |
| ---: | --- | --- | --- |
| 0 | `SWISS` | TUNX | Absent |
| 1 | `ROUND_ROBIN` | TURX | Absent |
| 2 | `TEAM_ROUND_ROBIN` | TUTX | Present |
| 3 | `TEAM_SWISS` | TUMX | Present |

The decoder uses this value, validates it against the directory structure, and
does not depend on the filename. Unknown type values are rejected.

The trailing directory is always 36 bytes, with seven uint32 values between the
directory and end markers. Team files use all five section offsets followed by
the directory offset and zero. Individual files contain schedule, player, and
game-section offsets, then the directory offset, then three zeros. There are no
empty team sections to skip in individual files.

Schedule entries retain 16 strings and 76 numeric bytes. Game/match counts at
numeric offsets 6 and 8 delimit each round's records. Individual match counts
must be zero. There is no assumption that all scheduled rounds are paired,
completed, or have the same record count. A zero schedule date yields `None` and
an empty time string remains empty; neither is filled from the event dates.

## Individual pairings

TUNX and TURX use the same 21-byte game records as team tournaments. Player
references are one-based indices into `Tournament.players`. Normal entries have
two positive references and the usual result codes 0–6. The second reference may
instead be `ffff` (-1, bye) or `fffe` (-2, not paired).

Abu Dhabi's completed byes use result code **9**, exposed as `GameResult.BYE`.
Their points are `(1.0, None)`: the nonexistent opponent has no score. Completed
not-paired entries use code 3, giving `(0.0, None)` without counting as played
games. A draw code for a special entry gives `(0.5, None)`; this case is tested
synthetically. Code 0 remains unreported, including future byes/exclusions, so
its points are `None`. Unknown result codes also remain unscored. Code 9 with
an ordinary opponent is retained but not scored.

Individual games have `match_number=None`. Their `board_number` is their
round-local pairing position for normal pairings, or `None` for special entries.
The `number` field includes every stored record, including exclusions. Individual
events return empty teams and round-match tuples. Player team and roster-board
fields are zero in the observed files.

The TUNX fixture has five completed rounds, a paired but unreported sixth round,
and only exclusion entries for round seven. It contains 258 pairing records;
that count is not a count of played games. Pairing uniqueness is checked within
each round, including special entries.

## Team round-robin board slots

TUTX stores a fixed block of `boards_per_match` games for each team match, in
match order. The Croatian league has five matches of six board slots per round.
Unassigned slots are `(white=0, black=0, result=0)`; future rounds contain only
such slots. Earlier rounds also contain empty blocks for a team without a roster.
These records must not be discarded or treated as reported 0–0 games.

The reader links these placeholders by their position in the fixed block and
checks any known players against the corresponding match's teams. It rejects
inconsistent block lengths, conflicting player/team references, duplicate
players, and nonzero results on entirely empty slots. Each game retains its raw
bytes and round/match/board position. A match containing unreported slots has
`board_points=None`.

TUMX continues to link games through the players' teams, including its one-sided
empty player slots; the fixed-block rule is not imposed on team Swiss files.

## Regression files and independent references

All fixtures remain local under `tests/fixtures/`, excluded from Git and archives.

| File | Players | Teams | Rounds | Pairing/board records |
| --- | ---: | ---: | ---: | ---: |
| `41st_abu_dhabi_amateur_chess_tournament_1498717__1_.TUNX` | 74 | 0 | 7 | 258 |
| `juvenil_femenino_c_1499104.TURX` | 6 | 0 | 5 | 15 |
| `4_hsl_jug_seniori_2026_jesenski_1356710.TUTX` | 138 | 10 | 9 | 270 |
| `olympiad2026open_1469895.TUMX` | 1025 | 206 | 11 | 4516 |

SHA-256 identifiers for the three added fixtures:

```text
TUNX fac89914da2949230eac5a6d2d273c1214760fe7b5fe6f7ed1b8c3fbdb54b5ce
TURX cb0053131cc919e28aa2ef382d995609a56a52947f098fcecd3ae2e0e0911a71
TUTX 82b75903e398d4708e6ef969ba5e2decb437420fe140b9e5a76872d845d43d6a
```

Published references retrieved September 28, 2026, saved as optional offline HTML
snapshots for independent score comparisons:

- [Abu Dhabi standings after round 5](https://chess-results.com/tnr1498717.aspx?lan=1&art=1&rd=5&zeilen=99999):
  `tunx-reference.html`, all 74 player totals, including the three reported byes.
- [Juvenil Femenino standings after round 5](https://chess-results.com/tnr1499104.aspx?lan=1&art=1&rd=5&zeilen=99999):
  `turx-reference.html`, all six player totals, including forfeits.
- [Croatian league crosstable](https://chess-results.com/tnr1356710.aspx?lan=1&art=0&rd=6&zeilen=99999):
  `tutx-reference.html`, board-point totals for all ten listed teams through round 6.

Every fixture also passes lossless reconstruction from its raw sections. These
checks verify the observed data; other software versions, result codes, scoring
systems, and pairing layouts still require independent examples. Application
settings and calculated rankings/tie-breaks remain subject to the limits in the
TUMX notes. The decoder performs no network requests.
