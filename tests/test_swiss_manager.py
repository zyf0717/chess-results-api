"""Shared layout, format differences, and local binary regressions."""

from collections import Counter
from pathlib import Path
from struct import pack_into

import pytest

from chess_results_api import (
    SwissManagerDecodeError,
    TournamentType,
    decode_tournament,
    load_tournament,
)
from chess_results_api.models import GameResult

from .helpers import (
    LOCAL_BINARIES,
    _document,
    _game,
    _marker,
    _match,
    _paired_document,
    _player,
    _schedule,
)


def _individual_document(**overrides: object) -> bytes:
    options = {
        "tournament_type": 0,
        "player": _player(0, board=0) * 2,
        "player_count": 2,
        "boards": 0,
        "round_count": 1,
        "schedule": _schedule(1, 0),
        "games": _game(),
    }
    return _document(**(options | overrides))


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


@pytest.mark.parametrize(
    "suffix,kind,players,teams,rounds,games",
    [
        ("TUNX", TournamentType.SWISS, 74, 0, 7, 258),
        ("TURX", TournamentType.ROUND_ROBIN, 6, 0, 5, 15),
        ("TUTX", TournamentType.TEAM_ROUND_ROBIN, 138, 10, 9, 270),
    ],
)
def test_local_new_binaries(
    suffix: str,
    kind: TournamentType,
    players: int,
    teams: int,
    rounds: int,
    games: int,
) -> None:
    path = Path(__file__).parent / "fixtures" / LOCAL_BINARIES[suffix]
    if not path.is_file():
        pytest.skip(f"Local {suffix} fixture is not distributed")
    data = path.read_bytes()
    tournament = decode_tournament(data)
    assert tournament.tournament_type == kind
    assert (len(tournament.players), len(tournament.teams), len(tournament.rounds)) == (
        players,
        teams,
        rounds,
    )
    assert sum(len(r.games) for r in tournament.rounds) == games
    assert b"".join(section.data for section in tournament.sections) == data
    if suffix == "TUNX":
        assert tournament.tournament_id == 1498717
        assert tournament.players[0].last_name == "Al-Sharif"
        assert tournament.metadata.text_fields[35] == "NA Noora Abdulsalam Alkhoori 9333711"
        assert [len(r.games) for r in tournament.rounds] == [38, 39, 41, 43, 43, 43, 11]
        assert all(g.points is None for r in tournament.rounds[5:] for g in r.games)
        byes = [g for r in tournament.rounds for g in r.games if g.result == GameResult.BYE]
        assert len(byes) == 3
        assert all(g.points == (1, None) and not g.played for g in byes)
    elif suffix == "TURX":
        assert tournament.tournament_id == 1499104
        assert tournament.players[0].first_name == "Gabriela"
        assert all(r.scheduled_date is None and r.start_time == "" for r in tournament.rounds)
        opponents = [
            frozenset((g.white_player, g.black_player)) for r in tournament.rounds for g in r.games
        ]
        assert len(set(opponents)) == 15
    else:
        assert tournament.tournament_id == 1356710
        assert tournament.configuration.boards_per_match == 6
        assert sum(len(r.matches) for r in tournament.rounds) == 45
        empty = Counter(r.number for r in tournament.rounds for g in r.games if not g.white_player)
        assert empty == {1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 30, 8: 30, 9: 30}
        assert all(m.board_points is None for r in tournament.rounds[6:] for m in r.matches)
