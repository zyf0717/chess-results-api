"""Optional local binary regressions for all supported formats."""

from collections import Counter

import pytest

from chess_results_api import TournamentType
from chess_results_api.models import GameResult, PartialDate

from .helpers import LOCAL_BINARIES, fixture_path, load_local_tournament


@pytest.mark.parametrize(
    "suffix,kind,players,teams,rounds,games",
    [
        ("TUNX", TournamentType.SWISS, 74, 0, 7, 258),
        ("TURX", TournamentType.ROUND_ROBIN, 6, 0, 5, 15),
        ("TUTX", TournamentType.TEAM_ROUND_ROBIN, 138, 10, 9, 270),
        ("TUMX", TournamentType.TEAM_SWISS, 1025, 206, 11, 4516),
    ],
)
def test_local_binary_structure(
    suffix: str,
    kind: TournamentType,
    players: int,
    teams: int,
    rounds: int,
    games: int,
) -> None:
    tournament = load_local_tournament(suffix)
    assert tournament.tournament_type == kind
    assert (len(tournament.players), len(tournament.teams), len(tournament.rounds)) == (
        players,
        teams,
        rounds,
    )
    assert sum(len(r.games) for r in tournament.rounds) == games
    assert (
        b"".join(section.data for section in tournament.sections)
        == fixture_path(LOCAL_BINARIES[suffix]).read_bytes()
    )


def test_local_abu_dhabi() -> None:
    tournament = load_local_tournament("TUNX")
    assert tournament.tournament_id == 1498717
    assert tournament.players[0].last_name == "Al-Sharif"
    assert tournament.metadata.text_fields[35] == "NA Noora Abdulsalam Alkhoori 9333711"
    assert [len(r.games) for r in tournament.rounds] == [38, 39, 41, 43, 43, 43, 11]
    assert all(g.points is None for r in tournament.rounds[5:] for g in r.games)
    byes = [g for r in tournament.rounds for g in r.games if g.result == GameResult.BYE]
    assert len(byes) == 3
    assert all(g.points == (1, None) and not g.played for g in byes)


def test_local_juvenil_femenino() -> None:
    tournament = load_local_tournament("TURX")
    assert tournament.tournament_id == 1499104
    assert tournament.players[0].first_name == "Gabriela"
    assert all(r.scheduled_date is None and r.start_time == "" for r in tournament.rounds)
    opponents = [
        frozenset((g.white_player, g.black_player)) for r in tournament.rounds for g in r.games
    ]
    assert len(set(opponents)) == 15


def test_local_croatian_league() -> None:
    tournament = load_local_tournament("TUTX")
    assert tournament.tournament_id == 1356710
    assert tournament.configuration.boards_per_match == 6
    assert sum(len(r.matches) for r in tournament.rounds) == 45
    empty = Counter(r.number for r in tournament.rounds for g in r.games if not g.white_player)
    assert empty == {1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 30, 8: 30, 9: 30}
    assert all(m.board_points is None for r in tournament.rounds[6:] for m in r.matches)


def test_local_olympiad() -> None:
    tournament = load_local_tournament("TUMX")
    assert tournament.tournament_id == 1469895
    assert tournament.metadata.name == "46th Chess Olympiad Samarkand 2026"
    assert tournament.metadata.section == "Open"
    assert tournament.metadata.location == "Samarkand"
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
    assert tournament.configuration.tie_break_codes == (13, 74, 1, 75)
    assert tournament.configuration.fide_event_id == 492113
    assert tournament.players[0].birth_date == PartialDate(1992, None, None)
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
