"""Synthetic format checks plus an optional regression against local source data."""

from pathlib import Path
from struct import pack, pack_into

import pytest

from chess_results_api.tumx import TumxDecodeError, decode_tumx, load_tumx


def _strings(*values: str) -> bytes:
    result = bytearray()
    for value in values:
        encoded = value.encode("utf-16-le")
        result.extend(pack("<H", len(encoded) // 2))
        result.extend(encoded)
    return bytes(result)


def _marker(value: int) -> bytes:
    return bytes((value, 0xFF, 0x89, 0x44))


def _document(*, player: bytes = b"", team: bytes = b"", name: str = "Test ♟") -> bytes:
    header = bytearray(108)
    header[:4] = _marker(0x93)
    pack_into("<I", header, 32, 12345)
    fields = [""] * 26
    fields[0], fields[1], fields[5] = name, "Open", "Samarkand"
    data = header + _strings(*fields) + bytes(212) + _marker(0x95) + bytes(32)
    offsets = []
    for marker, content in zip(
        (0xA3, 0xA5, 0xB3, 0xB5, 0xC3), (b"", player, b"", team, b""), strict=True
    ):
        offsets.append(len(data))
        data.extend(_marker(marker) + content)
    offsets.extend((len(data), 0))
    data.extend(_marker(0xD3) + pack("<7I", *offsets) + _marker(0xE3))
    return bytes(data)


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
