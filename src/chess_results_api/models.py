"""Typed records shared by the supported Swiss-Manager binary formats."""

from dataclasses import dataclass
from datetime import date
from enum import IntEnum


class TournamentType(IntEnum):
    """Tournament type stored in configuration, independent of the filename."""

    SWISS = 0
    ROUND_ROBIN = 1
    TEAM_ROUND_ROBIN = 2
    TEAM_SWISS = 3

    @property
    def is_team(self) -> bool:
        return self in (self.TEAM_ROUND_ROBIN, self.TEAM_SWISS)


@dataclass(frozen=True, slots=True)
class TournamentMetadata:
    """Recognized tournament text; all 132 text fields remain available by index."""

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
    tournament_type: TournamentType


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
    Number is the one-based record reference, not a calculated ranking.
    Individual events use zero for team_number and board_number.
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
    BYE = 9

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
            self.BYE: (1.0, 0.0),
        }.get(self)


@dataclass(frozen=True, slots=True)
class Game:
    """A board pairing; player numbers index the file's player records.

    Zero denotes an empty player slot, never the last player. For individual
    events black_player may be -1 (bye) or -2 (not paired); its points are None.
    match_number is None for individual events; board_number is also None for
    their special entries. Unknown result
    codes are retained and have no inferred score. `number` is round-local file
    order; board_number is the playing board within the match, not roster order.
    """

    number: int
    white_player: int
    black_player: int
    result_code: int
    match_number: int | None
    board_number: int | None
    raw_data: bytes

    @property
    def result(self) -> GameResult | None:
        try:
            return GameResult(self.result_code)
        except ValueError:
            return None

    @property
    def points(self) -> tuple[float, float | None] | None:
        result = self.result
        if result == GameResult.BYE and self.black_player != -1:
            return None
        points = None if result is None else result.points
        if points is not None and self.black_player < 0:
            return points[0], None
        return points

    @property
    def played(self) -> bool:
        return (
            self.white_player > 0
            and self.black_player > 0
            and self.result_code in (1, 2, 3)
        )


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

    @property
    def tournament_type(self) -> TournamentType:
        return self.configuration.tournament_type
