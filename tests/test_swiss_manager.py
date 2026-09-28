"""Shared binary layout, metadata, validation, and public entry points."""

from datetime import date
from pathlib import Path
from struct import pack_into

import pytest

from chess_results_api import (
    SwissManagerDecodeError,
    TournamentType,
    decode_tournament,
    load_tournament,
)
from chess_results_api.models import PartialDate

from .helpers import (
    _document,
    _game,
    _individual_document,
    _marker,
    _paired_document,
    _player,
    _schedule,
    _strings,
)


def test_empty_tournament_and_lossless_sections() -> None:
    data = _document()
    tournament = decode_tournament(data)
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
    assert decode_tournament(_document(name="棋赛 🏆")).metadata.name == "棋赛 🏆"


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
    tournament = decode_tournament(_document(player=player, team=team))
    assert len(tournament.players) == len(tournament.teams) == 1
    record = tournament.players[0]
    assert (record.last_name, record.first_name, record.display_name) == (
        "Example",
        "Zoë",
        "Z. Example",
    )
    assert (record.title, record.federation, record.rating) == ("IM", "UZB", 2400)
    assert (record.fide_id, record.team_number, record.board_number) == (
        123456789,
        1,
        4,
    )
    assert tournament.teams[record.team_number - 1].name == "Example team"
    assert tournament.teams[0].captain == "Captain"


def test_missing_identifiers_and_ratings_remain_zero() -> None:
    player = _strings("Example", *([""] * 17)) + bytes(134)
    record = decode_tournament(_document(player=player)).players[0]
    assert record.rating == record.fide_id == 0


@pytest.mark.parametrize(
    "data", [b"", b"not a Swiss-Manager file", bytes(200), _document()[:-1]]
)
def test_rejects_bad_envelopes(data: bytes) -> None:
    with pytest.raises(SwissManagerDecodeError):
        decode_tournament(data)


@pytest.mark.parametrize("index,value", [(0, 0), (1, 2**32 - 1), (5, 0), (6, 1)])
def test_rejects_bad_offsets(index: int, value: int) -> None:
    data = bytearray(_document())
    pack_into("<I", data, len(data) - 32 + 4 * index, value)
    with pytest.raises(SwissManagerDecodeError):
        decode_tournament(bytes(data))


def test_rejects_wrong_section_marker() -> None:
    data = _document().replace(_marker(0xA5), _marker(0xB5))
    with pytest.raises(SwissManagerDecodeError, match="section marker"):
        decode_tournament(data)


def test_rejects_unsupported_header_layout() -> None:
    data = _document().replace(_marker(0x95), bytes(4))
    with pytest.raises(SwissManagerDecodeError, match="header layout"):
        decode_tournament(data)


def test_rejects_invalid_utf16() -> None:
    data = bytearray(_document())
    data[110:112] = b"\x00\xd8"  # Unpaired high surrogate.
    with pytest.raises(SwissManagerDecodeError, match="Invalid UTF-16"):
        decode_tournament(bytes(data))


@pytest.mark.parametrize("record", [b"\xff\xff", _strings(*([""] * 18)) + bytes(133)])
def test_player_cannot_read_past_section_boundary(record: bytes) -> None:
    with pytest.raises(SwissManagerDecodeError, match="Truncated record"):
        decode_tournament(_document(player=record))


def test_team_cannot_read_past_section_boundary() -> None:
    with pytest.raises(SwissManagerDecodeError, match="Truncated record"):
        decode_tournament(_document(team=_strings(*([""] * 5)) + bytes(95)))


def test_load_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_tournament(tmp_path / "missing.bin")


def test_unknown_record_bytes_are_preserved() -> None:
    game = bytearray(_game())
    game[-1] = 123
    tournament = decode_tournament(_paired_document(games=bytes(game)))
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
    player = decode_tournament(_document(player=_player(0, birth_date=value))).players[
        0
    ]
    assert player.birth_date == expected


@pytest.mark.parametrize("value", [19930229, 20261301, 20000001, 99999999])
def test_invalid_birth_dates(value: int) -> None:
    with pytest.raises(SwissManagerDecodeError, match="Invalid date"):
        decode_tournament(_document(player=_player(0, birth_date=value)))


@pytest.mark.parametrize("value", [20260229, 20260000])
def test_invalid_schedule_dates(value: int) -> None:
    with pytest.raises(SwissManagerDecodeError, match="date"):
        decode_tournament(
            _paired_document(schedule=_schedule(1, 1, scheduled_date=value))
        )


def test_truncated_configuration() -> None:
    with pytest.raises(SwissManagerDecodeError, match="configuration"):
        decode_tournament(_document(configuration=_marker(0x95) + bytes(32)))


def test_configuration_fields() -> None:
    config = bytearray(1279)
    config[:4] = _marker(0x95)
    pack_into("<H", config, 15, 3)
    pack_into("<H", config, 31, 4)
    pack_into("<4H", config, 33, 13, 74, 1, 75)
    pack_into("<II", config, 75, 20260916, 20260927)
    pack_into("<I", config, 1275, 492113)
    result = decode_tournament(_document(configuration=bytes(config))).configuration
    assert result.tie_break_codes == (13, 74, 1, 75)
    assert result.start_date == date(2026, 9, 16)
    assert result.end_date == date(2026, 9, 27)
    assert result.fide_event_id == 492113
    assert result.raw_data == config


@pytest.mark.parametrize("kind", list(TournamentType))
def test_detects_type_from_contents(kind: TournamentType, tmp_path: Path) -> None:
    data = (
        _paired_document(tournament_type=kind)
        if kind.is_team
        else _individual_document(tournament_type=kind)
    )
    path = tmp_path / "no-format-extension.bin"
    path.write_bytes(data)
    tournament = load_tournament(path)
    assert tournament == decode_tournament(data)
    assert tournament.tournament_type is kind
    assert b"".join(section.data for section in tournament.sections) == data
    assert len(tournament.sections) == (8 if kind.is_team else 6)
    game = tournament.rounds[0].games[0]
    assert game.points == (1, 0)
    assert game.match_number == (1 if kind.is_team else None)
    assert game.board_number == 1
    if not kind.is_team:
        assert tournament.teams == tournament.rounds[0].matches == ()


def test_reads_all_header_strings() -> None:
    data = _individual_document(extra_header_text="Арбитр 🏆")
    metadata = decode_tournament(data).metadata
    assert len(metadata.text_fields) == 132
    assert metadata.text_fields[35] == "Арбитр 🏆"


def test_scheduled_round_count_is_independent_of_selected_round() -> None:
    config = bytearray(1279)
    config[:4] = _marker(0x95)
    pack_into("<H", config, 21, 1)
    pack_into("<H", config, 27, 2)
    tournament = decode_tournament(
        _document(
            tournament_type=0,
            configuration=bytes(config),
            schedule=_schedule(0, 0) * 2,
        )
    )
    assert tournament.configuration.round_count == len(tournament.rounds) == 2


@pytest.mark.parametrize("field,value", [(15, 99), (31, 10)])
def test_invalid_configuration_codes(field: int, value: int) -> None:
    config = bytearray(1279)
    config[:4] = _marker(0x95)
    pack_into("<H", config, field, value)
    with pytest.raises(SwissManagerDecodeError, match="Unsupported"):
        decode_tournament(_document(configuration=bytes(config), tournament_type=0))


def test_type_must_match_directory_shape() -> None:
    config = bytearray(1279)
    config[:4] = _marker(0x95)
    with pytest.raises(SwissManagerDecodeError, match="conflicts with directory"):
        decode_tournament(_document(configuration=bytes(config)))


def test_individual_rejects_team_settings() -> None:
    with pytest.raises(SwissManagerDecodeError, match="Team configuration"):
        decode_tournament(_individual_document(boards=4))


@pytest.mark.parametrize("index", [3, 4, 5, 6])
def test_individual_directory_validation(index: int) -> None:
    data = bytearray(_individual_document())
    pack_into("<I", data, len(data) - 32 + 4 * index, 1)
    with pytest.raises(SwissManagerDecodeError):
        decode_tournament(bytes(data))
