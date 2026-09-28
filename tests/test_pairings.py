"""Individual and team pairing rules across Swiss-Manager formats."""

from datetime import date

import pytest

from chess_results_api import (
    SwissManagerDecodeError,
    decode_tournament,
)
from chess_results_api.models import GameResult

from .helpers import (
    _document,
    _game,
    _individual_document,
    _match,
    _paired_document,
    _player,
    _schedule,
    _team,
)


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
    tournament = decode_tournament(_paired_document(games=_game(2, 1, code)))
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
    tournament = decode_tournament(_paired_document(games=game))
    assert tournament.rounds[0].matches[0].board_points == (
        (0, 1) if missing == "white" else (1, 0)
    )


@pytest.mark.parametrize("opponent,stored,points", [(-1, 4, (2, 0)), (-2, 0, (0, 0))])
def test_special_team_pairings(opponent: int, stored: int, points: tuple) -> None:
    tournament = decode_tournament(
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
    tournament = decode_tournament(_paired_document(boards=4))
    assert tournament.rounds[0].matches[0].board_points is None


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
    with pytest.raises(SwissManagerDecodeError, match=message):
        decode_tournament(_paired_document(**overrides))


@pytest.mark.parametrize(
    "opponent,result,points",
    [
        (-1, 9, (1, None)),
        (-1, 0, None),
        (-2, 3, (0, None)),
        (-2, 2, (0.5, None)),
        (-2, 0, None),
        (-2, 250, None),
    ],
)
def test_individual_special_pairings(opponent: int, result: int, points: tuple | None) -> None:
    game = (
        decode_tournament(_individual_document(games=_game(1, opponent, result))).rounds[0].games[0]
    )
    assert game.black_player == opponent
    assert game.points == points
    assert not game.played
    assert game.match_number is game.board_number is None


def test_bye_result_is_only_scored_for_a_bye_opponent() -> None:
    game = decode_tournament(_individual_document(games=_game(1, 2, 9))).rounds[0].games[0]
    assert game.result == GameResult.BYE
    assert game.points is None


@pytest.mark.parametrize("white,black", [(0, 2), (1, 0), (3, 2), (1, 3), (1, -3), (1, 1)])
def test_invalid_individual_references(white: int, black: int) -> None:
    with pytest.raises(SwissManagerDecodeError):
        decode_tournament(_individual_document(games=_game(white, black)))


def test_individual_player_cannot_also_be_unpaired_in_same_round() -> None:
    with pytest.raises(SwissManagerDecodeError, match="more than once"):
        decode_tournament(
            _individual_document(
                games=_game() + _game(1, -2, 3),
                schedule=_schedule(2, 0),
            )
        )


def test_round_robin_preserves_empty_board_slots() -> None:
    data = _paired_document(
        tournament_type=2,
        boards=2,
        schedule=_schedule(2, 1),
        games=_game() + _game(0, 0, 0),
    )
    tournament = decode_tournament(data)
    match = tournament.rounds[0].matches[0]
    assert match.board_points is None
    assert len(match.games) == 2
    empty = match.games[1]
    assert (empty.white_player, empty.black_player, empty.board_number) == (0, 0, 2)
    assert empty.points is None
    assert not empty.played
    assert b"".join(s.data for s in tournament.sections) == data


def test_round_robin_slots_must_match_configured_board_count() -> None:
    with pytest.raises(SwissManagerDecodeError, match="board slots"):
        decode_tournament(_paired_document(tournament_type=2, boards=2))


def test_round_robin_empty_board_cannot_have_result() -> None:
    with pytest.raises(SwissManagerDecodeError, match="empty board slot"):
        decode_tournament(_paired_document(tournament_type=2, games=_game(0, 0, 1)))


def test_round_robin_checks_slot_against_player_team() -> None:
    # Teams 1 and 2 occupy separate matches, so their players cannot face each other.
    with pytest.raises(SwissManagerDecodeError, match="match slot"):
        decode_tournament(
            _paired_document(
                tournament_type=2,
                schedule=_schedule(2, 2),
                games=_game() + _game(0, 0, 0),
                matches=_match(1, -1) + _match(2, -1),
            )
        )
