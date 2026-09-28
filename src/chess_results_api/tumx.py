"""Decode the binary TUMX layout observed in the 2026 Open Olympiad fixture.

This is an experimental, reverse-engineered reader, not a Swiss-Manager format
specification. Strings have a uint16 count of UTF-16 code units followed by
little-endian UTF-16. Numeric fields are little-endian. Unidentified application
settings remain available in original record bytes; see docs/tumx-format.md.
"""

from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from itertools import pairwise
from os import PathLike
from pathlib import Path
from struct import unpack_from

_MAGIC = b"\x93\xff\x89\x44"
_DIRECTORY = b"\xd3\xff\x89\x44"
_END = b"\xe3\xff\x89\x44"
_SECTION_MARKERS = (0xA3, 0xA5, 0xB3, 0xB5, 0xC3)
_SECTION_NAMES = ("schedule", "players", "player_pairings", "teams", "team_pairings")


class TumxDecodeError(ValueError):
    """The input is truncated, malformed, or uses an unsupported TUMX layout."""


@dataclass(frozen=True, slots=True)
class TournamentMetadata:
    """Recognized tournament text; all 26 text fields remain available by index."""

    name: str
    section: str
    remarks: str
    organizer: str
    location: str
    time_control: str
    federation: str
    chief_arbiter: str
    website: str
    text_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Configuration:
    """Recognized configuration fields, with the complete original record.

    Tie-break codes identify algorithms, not calculated standings. Their options
    and other application settings are retained in raw_data without interpretation.
    """

    round_count: int
    player_count: int
    team_count: int
    boards_per_match: int
    start_date: date | None
    end_date: date | None
    fide_event_id: int
    tie_break_codes: tuple[int, ...]
    raw_data: bytes


@dataclass(frozen=True, slots=True)
class PartialDate:
    """A date whose month and day may be unknown (e.g. a player's birth year)."""

    year: int
    month: int | None
    day: int | None


@dataclass(frozen=True, slots=True)
class Player:
    """Player record; team_number is a one-based index into Tournament.teams.

    Zero ratings and FIDE IDs are retained as stored, rather than imputed.
    Record order is not a ranking or a starting-number ordering.
    """

    last_name: str
    first_name: str
    display_name: str
    title: str
    federation: str
    rating: int
    fide_id: int
    team_number: int
    board_number: int
    number: int
    birth_date: PartialDate | None
    category: str
    sex_code: int
    text_fields: tuple[str, ...]
    numeric_data: bytes


@dataclass(frozen=True, slots=True)
class Team:
    """A team in file order; its one-based position is its team number."""

    name: str
    display_name: str
    captain: str
    federation: str
    group: str
    number: int
    text_fields: tuple[str, ...]
    numeric_data: bytes


class GameResult(IntEnum):
    """Recognized Swiss-Manager board result codes; forfeits are not played games."""

    UNREPORTED = 0
    WHITE_WIN = 1
    DRAW = 2
    BLACK_WIN = 3
    WHITE_FORFEIT_WIN = 4
    BLACK_FORFEIT_WIN = 5
    DOUBLE_FORFEIT = 6

    @property
    def points(self) -> tuple[float, float] | None:
        """White and black points under standard 1 / ½ / 0 board scoring."""
        return {
            self.WHITE_WIN: (1.0, 0.0),
            self.DRAW: (0.5, 0.5),
            self.BLACK_WIN: (0.0, 1.0),
            self.WHITE_FORFEIT_WIN: (1.0, 0.0),
            self.BLACK_FORFEIT_WIN: (0.0, 1.0),
            self.DOUBLE_FORFEIT: (0.0, 0.0),
        }.get(self)


@dataclass(frozen=True, slots=True)
class Game:
    """A board pairing; player numbers index the file's player records.

    Zero denotes an empty player slot, never the last player. Unknown result
    codes are retained and have no inferred score. `number` is round-local file
    order; board_number is the playing board within the match, not roster order.
    """

    number: int
    white_player: int
    black_player: int
    result_code: int
    match_number: int
    board_number: int
    raw_data: bytes

    @property
    def result(self) -> GameResult | None:
        try:
            return GameResult(self.result_code)
        except ValueError:
            return None

    @property
    def points(self) -> tuple[float, float] | None:
        return None if self.result is None else self.result.points

    @property
    def played(self) -> bool:
        return self.result_code in (1, 2, 3)


@dataclass(frozen=True, slots=True)
class TeamMatch:
    """Team pairing in displayed order, with linked games and board points.

    second_team == -1 is a bye; -2 means not paired. Stored board points are
    used for these entries. Ordinary matches are summed from board results;
    incomplete/unknown results produce None, not a fictitious zero score.
    No official rank, tie-break, or match-point calculation is implied.
    """

    number: int
    first_team: int
    second_team: int
    games: tuple[Game, ...]
    board_points: tuple[float, float] | None
    stored_board_points: tuple[float, float]
    raw_data: bytes


@dataclass(frozen=True, slots=True)
class Round:
    """One scheduled round. Start time is local text; the file supplies no zone."""

    number: int
    scheduled_date: date | None
    start_time: str
    games: tuple[Game, ...]
    matches: tuple[TeamMatch, ...]
    text_fields: tuple[str, ...]
    numeric_data: bytes


@dataclass(frozen=True, slots=True)
class RawSection:
    """An exact file slice, including its marker, at an absolute byte offset."""

    name: str
    offset: int
    data: bytes


@dataclass(frozen=True, slots=True)
class Tournament:
    """Decoded records and losslessly retained sections in file order."""

    tournament_id: int
    metadata: TournamentMetadata
    players: tuple[Player, ...]
    teams: tuple[Team, ...]
    sections: tuple[RawSection, ...]
    configuration: Configuration
    rounds: tuple[Round, ...]


class _Reader:
    def __init__(self, data: bytes, start: int, end: int) -> None:
        self.data = data
        self.position = start
        self.end = end

    def read(self, size: int) -> bytes:
        start = self.position
        if start + size > self.end:
            raise TumxDecodeError(f"Truncated record at byte {start}: need {size} bytes")
        self.position += size
        return self.data[start : self.position]

    def strings(self, count: int) -> tuple[str, ...]:
        fields = []
        for _ in range(count):
            size = int.from_bytes(self.read(2), "little") * 2
            start = self.position
            value = self.read(size)
            try:
                fields.append(value.decode("utf-16-le"))
            except UnicodeDecodeError as exc:
                raise TumxDecodeError(f"Invalid UTF-16 text at byte {start}") from exc
        return tuple(fields)


def _partial_date(value: int) -> PartialDate | None:
    if value == 0:
        return None
    year, remainder = divmod(value, 10000)
    month, day = divmod(remainder, 100)
    try:
        if day and not month:
            raise ValueError("day without month")
        date(year, month or 1, day or 1)
    except ValueError as exc:
        raise TumxDecodeError(f"Invalid date value {value}") from exc
    return PartialDate(year, month or None, day or None)


def _date(value: int) -> date | None:
    partial = _partial_date(value)
    if partial is None:
        return None
    if partial.month is None or partial.day is None:
        raise TumxDecodeError(f"Incomplete scheduled date {value}")
    return date(partial.year, partial.month, partial.day)


def _configuration(data: bytes) -> Configuration:
    if len(data) < 1279:
        raise TumxDecodeError("Truncated TUMX configuration")
    tie_break_count = unpack_from("<H", data, 31)[0]
    if tie_break_count > 9:
        raise TumxDecodeError("Unsupported number of tie-breaks")
    return Configuration(
        round_count=unpack_from("<H", data, 21)[0],
        player_count=unpack_from("<H", data, 23)[0],
        team_count=unpack_from("<H", data, 51)[0],
        boards_per_match=unpack_from("<H", data, 53)[0],
        start_date=_date(unpack_from("<I", data, 75)[0]),
        end_date=_date(unpack_from("<I", data, 79)[0]),
        fide_event_id=unpack_from("<I", data, 1275)[0],
        tie_break_codes=unpack_from(f"<{tie_break_count}H", data, 33),
        raw_data=data,
    )


def _match_points(
    games: tuple[Game, ...], first_team: int, players: tuple[Player, ...], boards: int
) -> tuple[float, float] | None:
    if not boards or len(games) != boards:
        return None
    first = second = 0.0
    for game in games:
        points = game.points
        if points is None:
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
            raise TumxDecodeError("Invalid team reference in pairing")
        for team in (first, second):
            if team > 0:
                if team in match_by_team:
                    raise TumxDecodeError("Team paired more than once in a round")
                match_by_team[team] = len(team_matches)
        team_matches.append((first, second, raw))

    grouped: list[list[Game]] = [[] for _ in team_matches]
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
                raise TumxDecodeError("Invalid player reference in pairing")
            if player in seen_players:
                raise TumxDecodeError("Player paired more than once in a round")
            seen_players.add(player)
            teams.append(players[player - 1].team_number)
        indexes = {match_by_team.get(team) for team in teams}
        if not teams or len(teams) != len(set(teams)) or None in indexes or len(indexes) != 1:
            raise TumxDecodeError("Board game does not identify a unique team match")
        index = match_by_team[teams[0]]
        if team_matches[index][1] < 0:
            raise TumxDecodeError("Board game assigned to a bye or unpaired team")
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
            raise TumxDecodeError("Too many board games in a team match")
        stored = tuple(value / 2 for value in unpack_from("<HH", raw, 4))
        stored_points = (stored[0], stored[1])
        match_games = tuple(group)
        points = (
            stored_points
            if second < 0
            else _match_points(match_games, first, players, configuration.boards_per_match)
        )
        matches.append(TeamMatch(number, first, second, match_games, points, stored_points, raw))
    return tuple(games), tuple(matches)


def _rounds(
    schedule: RawSection,
    game_section: RawSection,
    match_section: RawSection,
    players: tuple[Player, ...],
    configuration: Configuration,
) -> tuple[Round, ...]:
    reader = _Reader(schedule.data, 4, len(schedule.data))
    game_reader = _Reader(game_section.data, 4, len(game_section.data))
    match_reader = _Reader(match_section.data, 4, len(match_section.data))
    rounds = []
    while reader.position < reader.end:
        fields = reader.strings(16)
        numeric = reader.read(76)
        game_count, match_count = unpack_from("<HH", numeric, 6)
        game_data = game_reader.read(game_count * 21)
        match_data = match_reader.read(match_count * 15)
        games, matches = _round_pairings(game_data, match_data, players, configuration)
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
        raise TumxDecodeError("Round count does not match schedule")
    if game_reader.position != game_reader.end or match_reader.position != match_reader.end:
        raise TumxDecodeError("Pairing records left over after reading all rounds")
    return tuple(rounds)


def load_tumx(path: str | PathLike[str]) -> Tournament:
    """Read a local TUMX file; filesystem errors propagate unchanged."""
    return decode_tumx(Path(path).read_bytes())


def decode_tumx(data: bytes) -> Tournament:
    """Decode bytes using the observed TUMX layout.

    Raises TumxDecodeError for invalid boundaries, text, or section markers.
    Includes schedules, board results, and team matches with standard board scores.
    No filename, network connection, or optional dependency is required.
    """
    if len(data) < 144 or not data.startswith(_MAGIC):
        raise TumxDecodeError("Missing TUMX header or truncated file")
    directory = len(data) - 36
    if data[directory : directory + 4] != _DIRECTORY or data[-4:] != _END:
        raise TumxDecodeError("Missing TUMX directory or end marker")
    offsets = unpack_from("<7I", data, directory + 4)
    if offsets[5] != directory or offsets[6] != 0:
        raise TumxDecodeError("Unsupported TUMX directory layout")
    boundaries = (*offsets[:5], directory)
    if boundaries[0] <= 108 or any(a >= b for a, b in pairwise(boundaries)):
        raise TumxDecodeError("Invalid TUMX section offsets")
    for offset, marker in zip(boundaries[:-1], _SECTION_MARKERS, strict=True):
        if data[offset : offset + 4] != bytes((marker, 0xFF, 0x89, 0x44)):
            raise TumxDecodeError(f"Unexpected TUMX section marker at byte {offset}")

    reader = _Reader(data, 108, boundaries[0])
    fields = reader.strings(26)
    # The observed header contains 212 reserved bytes after its text fields.
    reader.read(212)
    configuration = reader.position
    if reader.read(4) != b"\x95\xff\x89\x44":
        raise TumxDecodeError("Unsupported TUMX header layout")
    settings = _configuration(data[configuration : boundaries[0]])
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
    reader = _Reader(data, boundaries[3] + 4, boundaries[4])
    while reader.position < reader.end:
        fields = reader.strings(5)
        tail = reader.read(96)
        teams.append(Team(*fields, number=len(teams) + 1, text_fields=fields, numeric_data=tail))

    if len(players) != settings.player_count or len(teams) != settings.team_count:
        raise TumxDecodeError("Player or team count does not match configuration")
    if any(not 0 <= player.team_number <= len(teams) for player in players):
        raise TumxDecodeError("Invalid player team reference")

    starts = (0, configuration, *boundaries, len(data))
    names = ("header", "configuration", *_SECTION_NAMES, "directory")
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
        rounds=_rounds(sections[2], sections[4], sections[6], tuple(players), settings),
    )
