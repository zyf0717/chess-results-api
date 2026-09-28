"""Synthetic format checks plus an optional regression against local source data."""

from datetime import date
from pathlib import Path
from struct import pack, pack_into

import pytest

from chess_results_api.tumx import GameResult, PartialDate, TumxDecodeError, decode_tumx, load_tumx


def _strings(*values: str) -> bytes:
    result = bytearray()
    for value in values:
        encoded = value.encode("utf-16-le")
        result.extend(pack("<H", len(encoded) // 2))
        result.extend(encoded)
    return bytes(result)


def _marker(value: int) -> bytes:
    return bytes((value, 0xFF, 0x89, 0x44))


def _document(
    *,
    player: bytes = b"",
    team: bytes = b"",
    name: str = "Test ♟",
    schedule: bytes = b"",
    games: bytes = b"",
    matches: bytes = b"",
    round_count: int = 0,
    player_count: int | None = None,
    team_count: int | None = None,
    boards: int = 4,
    configuration: bytes | None = None,
) -> bytes:
    header = bytearray(108)
    header[:4] = _marker(0x93)
    pack_into("<I", header, 32, 12345)
    fields = [""] * 26
    fields[0], fields[1], fields[5] = name, "Open", "Samarkand"
    if configuration is None:
        config = bytearray(1279)
        config[:4] = _marker(0x95)
        pack_into(
            "<HH",
            config,
            21,
            round_count,
            int(bool(player)) if player_count is None else player_count,
        )
        pack_into("<HH", config, 51, int(bool(team)) if team_count is None else team_count, boards)
        configuration = bytes(config)
    data = header + _strings(*fields) + bytes(212) + configuration
    offsets = []
    for marker, content in zip(
        (0xA3, 0xA5, 0xB3, 0xB5, 0xC3), (schedule, player, games, team, matches), strict=True
    ):
        offsets.append(len(data))
        data.extend(_marker(marker) + content)
    offsets.extend((len(data), 0))
    data.extend(_marker(0xD3) + pack("<7I", *offsets) + _marker(0xE3))
    return bytes(data)


def _player(team: int, *, birth_date: int = 0, board: int = 1) -> bytes:
    tail = bytearray(134)
    pack_into("<I", tail, 38, birth_date)
    pack_into("<HH", tail, 52, team, board)
    return _strings("Example", *([""] * 17)) + tail


def _team() -> bytes:
    return _strings("Team", "Team", "Captain", "UZB", "A") + bytes(96)


def _schedule(games: int, matches: int, *, scheduled_date: int = 20260916) -> bytes:
    tail = bytearray(76)
    pack_into("<I", tail, 0, scheduled_date)
    pack_into("<HH", tail, 6, games, matches)
    return _strings("15:00", *([""] * 15)) + tail


def _game(white: int = 1, black: int = 2, result: int = 1) -> bytes:
    return pack("<HHB16x", white, black, result)


def _match(first: int = 1, second: int = 2, first_half_points: int = 0) -> bytes:
    return pack("<HHHH7x", first, second & 65535, first_half_points, 0)


def _paired_document(**overrides: object) -> bytes:
    options = {
        "player": _player(1) + _player(2),
        "player_count": 2,
        "team": _team() * 2,
        "team_count": 2,
        "round_count": 1,
        "boards": 1,
        "schedule": _schedule(1, 1),
        "games": _game(),
        "matches": _match(),
    }
    return _document(**(options | overrides))


def test_empty_tournament_and_lossless_sections() -> None:
    data = _document()
    tournament = decode_tumx(data)
    assert tournament.tournament_id == 12345
    assert tournament.metadata.name == "Test ♟"
    assert tournament.metadata.section == "Open"
    assert tournament.metadata.location == "Samarkand"
    assert tournament.players == tournament.teams == ()
    assert b"".join(section.data for section in tournament.sections) == data
    assert [section.name for section in tournament.sections] == [
        "header",
        "configuration",
        "schedule",
        "players",
        "player_pairings",
        "teams",
        "team_pairings",
        "directory",
    ]
    for section in tournament.sections:
        assert data[section.offset : section.offset + len(section.data)] == section.data


def test_unicode_counts_utf16_code_units() -> None:
    assert decode_tumx(_document(name="棋赛 🏆")).metadata.name == "棋赛 🏆"


def test_player_and_team_fields() -> None:
    fields = [""] * 18
    fields[0], fields[1], fields[3], fields[4], fields[10] = (
        "Example",
        "Zoë",
        "Z. Example",
        "IM",
        "UZB",
    )
    tail = bytearray(134)
    pack_into("<H", tail, 32, 2400)
    pack_into("<IHH", tail, 48, 123456789, 1, 4)
    player = _strings(*fields) + tail
    team = _strings("Example team", "Example", "Captain", "UZB", "A") + bytes(96)
    tournament = decode_tumx(_document(player=player, team=team))
    assert len(tournament.players) == len(tournament.teams) == 1
    record = tournament.players[0]
    assert (record.last_name, record.first_name, record.display_name) == (
        "Example",
        "Zoë",
        "Z. Example",
    )
    assert (record.title, record.federation, record.rating) == ("IM", "UZB", 2400)
    assert (record.fide_id, record.team_number, record.board_number) == (123456789, 1, 4)
    assert tournament.teams[record.team_number - 1].name == "Example team"
    assert tournament.teams[0].captain == "Captain"


def test_missing_identifiers_and_ratings_remain_zero() -> None:
    player = _strings("Example", *([""] * 17)) + bytes(134)
    record = decode_tumx(_document(player=player)).players[0]
    assert record.rating == record.fide_id == 0


@pytest.mark.parametrize("data", [b"", b"not a TUMX file", bytes(200), _document()[:-1]])
def test_rejects_bad_envelopes(data: bytes) -> None:
    with pytest.raises(TumxDecodeError):
        decode_tumx(data)


@pytest.mark.parametrize("index,value", [(0, 0), (1, 2**32 - 1), (5, 0), (6, 1)])
def test_rejects_bad_offsets(index: int, value: int) -> None:
    data = bytearray(_document())
    pack_into("<I", data, len(data) - 32 + 4 * index, value)
    with pytest.raises(TumxDecodeError):
        decode_tumx(bytes(data))


def test_rejects_wrong_section_marker() -> None:
    data = _document().replace(_marker(0xA5), _marker(0xB5))
    with pytest.raises(TumxDecodeError, match="section marker"):
        decode_tumx(data)


def test_rejects_unsupported_header_layout() -> None:
    data = _document().replace(_marker(0x95), bytes(4))
    with pytest.raises(TumxDecodeError, match="header layout"):
        decode_tumx(data)


def test_rejects_invalid_utf16() -> None:
    data = bytearray(_document())
    data[110:112] = b"\x00\xd8"  # Unpaired high surrogate.
    with pytest.raises(TumxDecodeError, match="Invalid UTF-16"):
        decode_tumx(bytes(data))


@pytest.mark.parametrize("record", [b"\xff\xff", _strings(*([""] * 18)) + bytes(133)])
def test_player_cannot_read_past_section_boundary(record: bytes) -> None:
    with pytest.raises(TumxDecodeError, match="Truncated record"):
        decode_tumx(_document(player=record))


def test_team_cannot_read_past_section_boundary() -> None:
    with pytest.raises(TumxDecodeError, match="Truncated record"):
        decode_tumx(_document(team=_strings(*([""] * 5)) + bytes(95)))


def test_load_path(tmp_path: Path) -> None:
    path = tmp_path / "example.TUMX"
    path.write_bytes(_document())
    assert load_tumx(path) == decode_tumx(path.read_bytes())


def test_load_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_tumx(tmp_path / "missing.TUMX")


@pytest.mark.parametrize(
    "code,points,played",
    [
        (0, None, False),
        (1, (1, 0), True),
        (2, (0.5, 0.5), True),
        (3, (0, 1), True),
        (4, (1, 0), False),
        (5, (0, 1), False),
        (6, (0, 0), False),
        (250, None, False),
    ],
)
def test_results_and_team_orientation(code: int, points: tuple | None, played: bool) -> None:
    tournament = decode_tumx(_paired_document(games=_game(2, 1, code)))
    round_ = tournament.rounds[0]
    game = round_.games[0]
    assert game.points == points
    assert game.played is played
    assert game.result == (GameResult(code) if code < 7 else None)
    assert (game.number, game.match_number, game.board_number) == (1, 1, 1)
    assert round_.matches[0].games == (game,)
    assert round_.matches[0].board_points == (None if points is None else points[::-1])
    assert round_.scheduled_date == date(2026, 9, 16)
    assert round_.start_time == "15:00"


@pytest.mark.parametrize("missing", ["white", "black"])
def test_empty_player_slot_keeps_game_and_team_score(missing: str) -> None:
    game = _game(0, 2, 5) if missing == "white" else _game(1, 0, 4)
    tournament = decode_tumx(_paired_document(games=game))
    assert tournament.rounds[0].matches[0].board_points == (
        (0, 1) if missing == "white" else (1, 0)
    )


@pytest.mark.parametrize("opponent,stored,points", [(-1, 4, (2, 0)), (-2, 0, (0, 0))])
def test_special_team_pairings(opponent: int, stored: int, points: tuple) -> None:
    tournament = decode_tumx(
        _document(
            team=_team(),
            round_count=1,
            schedule=_schedule(0, 1),
            matches=_match(1, opponent, stored),
        )
    )
    match = tournament.rounds[0].matches[0]
    assert match.second_team == opponent
    assert match.board_points == match.stored_board_points == points
    assert match.games == ()


def test_incomplete_match_has_no_total() -> None:
    tournament = decode_tumx(_paired_document(boards=4))
    assert tournament.rounds[0].matches[0].board_points is None


def test_unknown_record_bytes_are_preserved() -> None:
    game = bytearray(_game())
    game[-1] = 123
    tournament = decode_tumx(_paired_document(games=bytes(game)))
    assert tournament.rounds[0].games[0].raw_data == game
    assert tournament.players[0].numeric_data == _player(1)[-134:]
    assert tournament.teams[0].numeric_data == bytes(96)
    assert tournament.rounds[0].numeric_data == _schedule(1, 1)[-76:]


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, None),
        (19920000, PartialDate(1992, None, None)),
        (19920700, PartialDate(1992, 7, None)),
        (20000229, PartialDate(2000, 2, 29)),
    ],
)
def test_partial_birth_dates(value: int, expected: PartialDate | None) -> None:
    player = decode_tumx(_document(player=_player(0, birth_date=value))).players[0]
    assert player.birth_date == expected


@pytest.mark.parametrize("value", [19930229, 20261301, 20000001, 99999999])
def test_invalid_birth_dates(value: int) -> None:
    with pytest.raises(TumxDecodeError, match="Invalid date"):
        decode_tumx(_document(player=_player(0, birth_date=value)))


@pytest.mark.parametrize("value", [20260229, 20260000])
def test_invalid_schedule_dates(value: int) -> None:
    with pytest.raises(TumxDecodeError, match="date"):
        decode_tumx(_paired_document(schedule=_schedule(1, 1, scheduled_date=value)))


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"player_count": 3}, "count"),
        ({"team_count": 3}, "count"),
        ({"round_count": 2}, "Round count"),
        ({"games": _game()[:-1]}, "Truncated"),
        ({"matches": _match()[:-1]}, "Truncated"),
        ({"schedule": _schedule(1, 1)[:-1]}, "Truncated"),
        ({"games": _game() + bytes(21)}, "left over"),
        ({"matches": _match() + bytes(15)}, "left over"),
        ({"games": _game(3, 2)}, "player reference"),
        ({"games": _game(1, 1)}, "Player paired more than once"),
        ({"games": _game(0, 0)}, "unique team match"),
        ({"matches": _match(1, 3)}, "team reference"),
        ({"matches": _match(1, 1)}, "Team paired more than once"),
        ({"matches": _match(1, -1), "games": _game(1, 0)}, "bye or unpaired"),
        ({"player": _player(3) + _player(2)}, "player team reference"),
        ({"player": _player(1) * 2}, "unique team match"),
        ({"boards": 0}, "Too many board games"),
    ],
)
def test_invalid_round_records(overrides: dict, message: str) -> None:
    with pytest.raises(TumxDecodeError, match=message):
        decode_tumx(_paired_document(**overrides))


def test_truncated_configuration() -> None:
    with pytest.raises(TumxDecodeError, match="configuration"):
        decode_tumx(_document(configuration=_marker(0x95) + bytes(32)))


def test_configuration_fields() -> None:
    config = bytearray(1279)
    config[:4] = _marker(0x95)
    pack_into("<H", config, 31, 4)
    pack_into("<4H", config, 33, 13, 74, 1, 75)
    pack_into("<II", config, 75, 20260916, 20260927)
    pack_into("<I", config, 1275, 492113)
    result = decode_tumx(_document(configuration=bytes(config))).configuration
    assert result.tie_break_codes == (13, 74, 1, 75)
    assert result.start_date == date(2026, 9, 16)
    assert result.end_date == date(2026, 9, 27)
    assert result.fide_event_id == 492113
    assert result.raw_data == config


def test_local_olympiad_fixture() -> None:
    path = Path(__file__).parent / "fixtures" / "olympiad2026open_1469895.TUMX"
    if not path.is_file():
        pytest.skip("Local TUMX fixture is not distributed; see README.md")
    tournament = load_tumx(path)
    assert tournament.tournament_id == 1469895
    assert tournament.metadata.name == "46th Chess Olympiad Samarkand 2026"
    assert tournament.metadata.section == "Open"
    assert tournament.metadata.location == "Samarkand"
    assert len(tournament.players) == 1025
    assert len(tournament.teams) == 206
    caruana = tournament.players[0]
    assert (caruana.last_name, caruana.first_name, caruana.title) == ("Caruana", "Fabiano", "GM")
    assert (caruana.rating, caruana.fide_id, caruana.team_number, caruana.board_number) == (
        2789,
        2020009,
        1,
        1,
    )
    assert tournament.teams[0].name == "United States of America"
    assert tournament.players[-1].last_name == "Singhateh"
    assert all(1 <= player.team_number <= 206 for player in tournament.players)
    assert all(1 <= player.board_number <= 5 for player in tournament.players)
    assert all(
        player.federation == tournament.teams[player.team_number - 1].federation
        for player in tournament.players
    )
    assert b"".join(section.data for section in tournament.sections) == path.read_bytes()
    assert tournament.configuration.tie_break_codes == (13, 74, 1, 75)
    assert tournament.configuration.fide_event_id == 492113
    assert tournament.players[0].birth_date == PartialDate(1992, None, None)
    assert len(tournament.rounds) == 11
    assert sum(len(r.games) for r in tournament.rounds) == 4516
    assert sum(len(r.matches) for r in tournament.rounds) == 1137
    assert [r.scheduled_date.day for r in tournament.rounds] == [
        16,
        17,
        18,
        19,
        20,
        21,
        23,
        24,
        25,
        26,
        27,
    ]
    assert tournament.rounds[-1].start_time == "11:00"
    first = tournament.rounds[0].matches[0]
    assert (first.first_team, first.second_team, first.board_points) == (105, 3, (0, 4))
    bye = tournament.rounds[2].matches[102]
    assert (bye.first_team, bye.second_team, bye.board_points) == (205, -1, (2, 0))
    empty_slots = [
        g for r in tournament.rounds for g in r.games if not all((g.white_player, g.black_player))
    ]
    assert len(empty_slots) == 2
    assert all(g.match_number == 56 for g in empty_slots)
    assert tournament.rounds[9].matches[55].board_points == (0, 4)
    totals = [0.0] * 207
    for round_ in tournament.rounds:
        for match in round_.matches:
            assert match.board_points is not None
            totals[match.first_team] += match.board_points[0]
            if match.second_team > 0:
                totals[match.second_team] += match.board_points[1]
            assert len(match.games) == (4 if match.second_team > 0 else 0)
    # Published final standings (art=0), including the bye and empty-player cases.
    assert {n: totals[n] for n in (1, 2, 3, 94, 205, 206)} == {
        1: 29.0,
        2: 28.5,
        3: 32.5,
        94: 21.5,
        205: 16.5,
        206: 1.5,
    }
