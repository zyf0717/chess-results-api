"""Decode Swiss-Manager TUNX, TURX, TUTX, and TUMX tournament files."""

from itertools import pairwise
from os import PathLike
from pathlib import Path
from struct import unpack_from

from ._binary import SwissManagerDecodeError, _date, _partial_date, _Reader
from .models import (
    Configuration,
    Game,
    Player,
    RawSection,
    Round,
    Team,
    TeamMatch,
    Tournament,
    TournamentMetadata,
    TournamentType,
)

_MAGIC = b"\x93\xff\x89\x44"
_DIRECTORY = b"\xd3\xff\x89\x44"
_END = b"\xe3\xff\x89\x44"


def _configuration(data: bytes) -> Configuration:
    if len(data) < 1279:
        raise SwissManagerDecodeError("Truncated tournament configuration")
    code = unpack_from("<H", data, 15)[0]
    try:
        tournament_type = TournamentType(code)
    except ValueError as exc:
        raise SwissManagerDecodeError(f"Unsupported tournament type {code}") from exc
    tie_break_count = unpack_from("<H", data, 31)[0]
    if tie_break_count > 9:
        raise SwissManagerDecodeError("Unsupported number of tie-breaks")
    return Configuration(
        round_count=unpack_from("<H", data, 27)[0],
        player_count=unpack_from("<H", data, 23)[0],
        team_count=unpack_from("<H", data, 51)[0],
        boards_per_match=unpack_from("<H", data, 53)[0],
        start_date=_date(unpack_from("<I", data, 75)[0]),
        end_date=_date(unpack_from("<I", data, 79)[0]),
        fide_event_id=unpack_from("<I", data, 1275)[0],
        tie_break_codes=unpack_from(f"<{tie_break_count}H", data, 33),
        raw_data=data,
        tournament_type=tournament_type,
    )


def _match_points(
    games: tuple[Game, ...], first_team: int, players: tuple[Player, ...], boards: int
) -> tuple[float, float] | None:
    if not boards or len(games) != boards:
        return None
    first = second = 0.0
    for game in games:
        points = game.points
        if points is None or points[1] is None:
            return None
        # With an empty white slot, use the known black player's team.
        white_is_first = (
            players[game.white_player - 1].team_number == first_team
            if game.white_player
            else players[game.black_player - 1].team_number != first_team
        )
        a, b = points if white_is_first else points[::-1]
        first += a
        second += b
    return first, second


def _round_pairings(
    game_data: bytes,
    match_data: bytes,
    players: tuple[Player, ...],
    configuration: Configuration,
) -> tuple[tuple[Game, ...], tuple[TeamMatch, ...]]:
    team_matches: list[tuple[int, int, bytes]] = []
    match_by_team: dict[int, int] = {}
    for offset in range(0, len(match_data), 15):
        raw = match_data[offset : offset + 15]
        first, second = unpack_from("<HH", raw)
        if second in (65534, 65535):
            second -= 65536
        if not 1 <= first <= configuration.team_count or not (
            1 <= second <= configuration.team_count or second in (-1, -2)
        ):
            raise SwissManagerDecodeError("Invalid team reference in pairing")
        for team in (first, second):
            if team > 0:
                if team in match_by_team:
                    raise SwissManagerDecodeError(
                        "Team paired more than once in a round"
                    )
                match_by_team[team] = len(team_matches)
        team_matches.append((first, second, raw))

    grouped: list[list[Game]] = [[] for _ in team_matches]
    fixed_boards = configuration.tournament_type == TournamentType.TEAM_ROUND_ROBIN
    if fixed_boards and (
        not configuration.boards_per_match
        or len(game_data) != len(team_matches) * configuration.boards_per_match * 21
    ):
        raise SwissManagerDecodeError(
            "Round-robin board slots do not match team pairings"
        )
    games = []
    seen_players: set[int] = set()
    for offset in range(0, len(game_data), 21):
        raw = game_data[offset : offset + 21]
        white, black, result = unpack_from("<HHB", raw)
        teams = []
        for player in (white, black):
            if player == 0:
                continue
            if player > len(players):
                raise SwissManagerDecodeError("Invalid player reference in pairing")
            if player in seen_players:
                raise SwissManagerDecodeError("Player paired more than once in a round")
            seen_players.add(player)
            teams.append(players[player - 1].team_number)
        indexes = {match_by_team.get(team) for team in teams}
        if fixed_boards:
            index = offset // 21 // configuration.boards_per_match
            if teams and (indexes != {index} or len(teams) != len(set(teams))):
                raise SwissManagerDecodeError(
                    "Board game conflicts with its round-robin match slot"
                )
            if not teams and result != 0:
                raise SwissManagerDecodeError("Result reported for an empty board slot")
        else:
            if (
                not teams
                or len(teams) != len(set(teams))
                or None in indexes
                or len(indexes) != 1
            ):
                raise SwissManagerDecodeError(
                    "Board game does not identify a unique team match"
                )
            index = match_by_team[teams[0]]
        if team_matches[index][1] < 0:
            raise SwissManagerDecodeError(
                "Board game assigned to a bye or unpaired team"
            )
        game = Game(
            number=len(games) + 1,
            white_player=white,
            black_player=black,
            result_code=result,
            match_number=index + 1,
            board_number=len(grouped[index]) + 1,
            raw_data=raw,
        )
        grouped[index].append(game)
        games.append(game)

    matches = []
    for number, ((first, second, raw), group) in enumerate(
        zip(team_matches, grouped, strict=True), start=1
    ):
        if len(group) > configuration.boards_per_match:
            raise SwissManagerDecodeError("Too many board games in a team match")
        stored = tuple(value / 2 for value in unpack_from("<HH", raw, 4))
        stored_points = (stored[0], stored[1])
        match_games = tuple(group)
        points = (
            stored_points
            if second < 0
            else _match_points(
                match_games, first, players, configuration.boards_per_match
            )
        )
        matches.append(
            TeamMatch(number, first, second, match_games, points, stored_points, raw)
        )
    return tuple(games), tuple(matches)


def _individual_pairings(data: bytes, player_count: int) -> tuple[Game, ...]:
    games = []
    seen: set[int] = set()
    for offset in range(0, len(data), 21):
        raw = data[offset : offset + 21]
        white, black, result = unpack_from("<HHB", raw)
        if black in (65534, 65535):
            black -= 65536
        if not 1 <= white <= player_count or not (
            1 <= black <= player_count or black in (-1, -2)
        ):
            raise SwissManagerDecodeError(
                "Invalid player reference in individual pairing"
            )
        for player in (white, black):
            if player > 0:
                if player in seen:
                    raise SwissManagerDecodeError(
                        "Player paired more than once in a round"
                    )
                seen.add(player)
        number = len(games) + 1
        games.append(
            Game(number, white, black, result, None, number if black > 0 else None, raw)
        )
    return tuple(games)


def _rounds(
    schedule: RawSection,
    game_section: RawSection,
    match_section: RawSection | None,
    players: tuple[Player, ...],
    configuration: Configuration,
) -> tuple[Round, ...]:
    reader = _Reader(schedule.data, 4, len(schedule.data))
    game_reader = _Reader(game_section.data, 4, len(game_section.data))
    match_data = b"" if match_section is None else match_section.data[4:]
    match_reader = _Reader(match_data, 0, len(match_data))
    rounds = []
    while reader.position < reader.end:
        fields = reader.strings(16)
        numeric = reader.read(76)
        game_count, match_count = unpack_from("<HH", numeric, 6)
        game_data = game_reader.read(game_count * 21)
        match_data = match_reader.read(match_count * 15)
        if configuration.tournament_type.is_team:
            games, matches = _round_pairings(
                game_data, match_data, players, configuration
            )
        else:
            games = _individual_pairings(game_data, len(players))
            matches = ()
        rounds.append(
            Round(
                number=len(rounds) + 1,
                scheduled_date=_date(unpack_from("<I", numeric)[0]),
                start_time=fields[0],
                games=games,
                matches=matches,
                text_fields=fields,
                numeric_data=numeric,
            )
        )
    if len(rounds) != configuration.round_count:
        raise SwissManagerDecodeError("Round count does not match schedule")
    if (
        game_reader.position != game_reader.end
        or match_reader.position != match_reader.end
    ):
        raise SwissManagerDecodeError(
            "Pairing records left over after reading all rounds"
        )
    return tuple(rounds)


def load_tournament(path: str | PathLike[str]) -> Tournament:
    """Read a local Swiss-Manager binary; filesystem errors propagate unchanged."""
    return decode_tournament(Path(path).read_bytes())


def decode_tournament(data: bytes) -> Tournament:
    """Decode TUNX, TURX, TUTX, or TUMX bytes, detecting type from configuration.

    The observed layouts share strings, participant records, and schedule records.
    Individual events omit team sections. Unknown fields remain available verbatim.
    Raises SwissManagerDecodeError for invalid or unsupported structure.
    """
    if len(data) < 144 or not data.startswith(_MAGIC):
        raise SwissManagerDecodeError("Missing Swiss-Manager header or truncated file")
    directory = len(data) - 36
    if data[directory : directory + 4] != _DIRECTORY or data[-4:] != _END:
        raise SwissManagerDecodeError("Missing tournament directory or end marker")
    offsets = unpack_from("<7I", data, directory + 4)
    has_teams = offsets[4] != 0 or offsets[5] != 0
    if has_teams:
        if offsets[5] != directory or offsets[6] != 0:
            raise SwissManagerDecodeError("Unsupported tournament directory layout")
        boundaries = (*offsets[:5], directory)
        markers = (0xA3, 0xA5, 0xB3, 0xB5, 0xC3)
        section_names = (
            "schedule",
            "players",
            "player_pairings",
            "teams",
            "team_pairings",
        )
    else:
        if offsets[3] != directory or offsets[6] != 0:
            raise SwissManagerDecodeError("Unsupported tournament directory layout")
        boundaries = (*offsets[:3], directory)
        markers = (0xA3, 0xA5, 0xB3)
        section_names = ("schedule", "players", "player_pairings")
    if boundaries[0] <= 108 or any(a >= b for a, b in pairwise(boundaries)):
        raise SwissManagerDecodeError("Invalid tournament section offsets")
    for offset, marker in zip(boundaries[:-1], markers, strict=True):
        if data[offset : offset + 4] != bytes((marker, 0xFF, 0x89, 0x44)):
            raise SwissManagerDecodeError(
                f"Unexpected tournament section marker at byte {offset}"
            )

    reader = _Reader(data, 108, boundaries[0])
    fields = reader.strings(132)
    configuration = reader.position
    if reader.read(4) != b"\x95\xff\x89\x44":
        raise SwissManagerDecodeError("Unsupported tournament header layout")
    settings = _configuration(data[configuration : boundaries[0]])
    if settings.tournament_type.is_team != has_teams:
        raise SwissManagerDecodeError(
            "Tournament type conflicts with directory sections"
        )
    if not has_teams and (settings.team_count or settings.boards_per_match):
        raise SwissManagerDecodeError(
            "Team configuration found in an individual tournament"
        )
    metadata = TournamentMetadata(
        name=fields[0],
        section=fields[1],
        remarks=fields[2],
        organizer=fields[4],
        location=fields[5],
        time_control=fields[14],
        federation=fields[20],
        chief_arbiter=fields[21],
        website=fields[24],
        text_fields=fields,
    )
    players = []
    reader = _Reader(data, boundaries[1] + 4, boundaries[2])
    while reader.position < reader.end:
        fields = reader.strings(18)
        # Fixed tail includes reserved fields; only identified values are exposed.
        tail = reader.read(134)
        players.append(
            Player(
                last_name=fields[0],
                first_name=fields[1],
                display_name=fields[3],
                title=fields[4],
                federation=fields[10],
                rating=unpack_from("<H", tail, 32)[0],
                fide_id=unpack_from("<I", tail, 48)[0],
                team_number=unpack_from("<H", tail, 52)[0],
                board_number=unpack_from("<H", tail, 54)[0],
                number=len(players) + 1,
                birth_date=_partial_date(unpack_from("<I", tail, 38)[0]),
                category=fields[11],
                sex_code=unpack_from("<H", tail, 30)[0],
                text_fields=fields,
                numeric_data=tail,
            )
        )

    teams = []
    if has_teams:
        reader = _Reader(data, boundaries[3] + 4, boundaries[4])
        while reader.position < reader.end:
            fields = reader.strings(5)
            tail = reader.read(96)
            teams.append(
                Team(
                    *fields,
                    number=len(teams) + 1,
                    text_fields=fields,
                    numeric_data=tail,
                )
            )

    if len(players) != settings.player_count or len(teams) != settings.team_count:
        raise SwissManagerDecodeError(
            "Player or team count does not match configuration"
        )
    if any(not 0 <= player.team_number <= len(teams) for player in players):
        raise SwissManagerDecodeError("Invalid player team reference")

    starts = (0, configuration, *boundaries, len(data))
    names = ("header", "configuration", *section_names, "directory")
    sections = tuple(
        RawSection(name, start, data[start:end])
        for name, (start, end) in zip(names, pairwise(starts), strict=True)
    )
    return Tournament(
        tournament_id=unpack_from("<I", data, 32)[0],
        metadata=metadata,
        players=tuple(players),
        teams=tuple(teams),
        sections=sections,
        configuration=settings,
        rounds=_rounds(
            sections[2],
            sections[4],
            sections[6] if has_teams else None,
            tuple(players),
            settings,
        ),
    )
