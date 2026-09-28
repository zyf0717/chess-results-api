"""Small synthetic encoders for the observed Swiss-Manager records."""

from struct import pack, pack_into

LOCAL_BINARIES = {
    "TUNX": "41st_abu_dhabi_amateur_chess_tournament_1498717__1_.TUNX",
    "TURX": "juvenil_femenino_c_1499104.TURX",
    "TUTX": "4_hsl_jug_seniori_2026_jesenski_1356710.TUTX",
}


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
    tournament_type: int = 3,
    extra_header_text: str = "",
) -> bytes:
    header = bytearray(108)
    header[:4] = _marker(0x93)
    pack_into("<I", header, 32, 12345)
    fields = [""] * 132
    fields[0], fields[1], fields[5] = name, "Open", "Samarkand"
    fields[35] = extra_header_text
    if configuration is None:
        config = bytearray(1279)
        config[:4] = _marker(0x95)
        pack_into("<H", config, 15, tournament_type)
        pack_into("<H", config, 27, round_count)
        pack_into(
            "<HH",
            config,
            21,
            round_count,
            int(bool(player)) if player_count is None else player_count,
        )
        pack_into("<HH", config, 51, int(bool(team)) if team_count is None else team_count, boards)
        configuration = bytes(config)
    data = header + _strings(*fields) + configuration
    offsets = []
    markers = (0xA3, 0xA5, 0xB3, 0xB5, 0xC3)
    contents = (schedule, player, games, team, matches)
    if tournament_type in (0, 1):
        markers, contents = markers[:3], contents[:3]
    for marker, content in zip(markers, contents, strict=True):
        offsets.append(len(data))
        data.extend(_marker(marker) + content)
    offsets.append(len(data))
    offsets.extend([0] * (7 - len(offsets)))
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
    return pack("<HHB16x", white, black & 65535, result)


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
