"""Independent, offline comparison against an optional published HTML snapshot."""

import re
from html import unescape
from pathlib import Path

import pytest

from .helpers import fixture_path, load_local_tournament


def _rows(path: Path) -> list[list[str]]:
    """Read cells from fixed reference snapshots, not arbitrary live pages."""
    return [
        [
            " ".join(unescape(re.sub("<[^>]*>", " ", cell)).split())
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", path.read_text("utf-8-sig"), re.S)
    ]


def test_local_published_board_point_totals() -> None:
    reference = fixture_path("standings-reference.html")
    tournament = load_local_tournament("TUMX")
    totals = {team.number: 0.0 for team in tournament.teams}
    for round_ in tournament.rounds:
        for match in round_.matches:
            assert match.board_points is not None
            totals[match.first_team] += match.board_points[0]
            if match.second_team > 0:
                totals[match.second_team] += match.board_points[1]

    expected = {}
    for cells in _rows(reference):
        if len(cells) == 14 and cells[0].isdigit() and cells[1].isdigit():
            number = int(cells[1])
            assert number not in expected
            expected[number] = float(cells[-2].replace(",", "."))
    assert len(expected) == 206
    assert totals == expected


@pytest.mark.parametrize("suffix,count", [("TUNX", 74), ("TURX", 6), ("TUTX", 10)])
def test_published_scores(suffix: str, count: int) -> None:
    reference = fixture_path(f"{suffix.lower()}-reference.html")
    tournament = load_local_tournament(suffix)
    expected = {}
    if tournament.tournament_type.is_team:
        totals = {team.name: 0.0 for team in tournament.teams}
        for round_ in tournament.rounds:
            for match in round_.matches:
                if match.board_points is not None:
                    totals[tournament.teams[match.first_team - 1].name] += match.board_points[0]
                    totals[tournament.teams[match.second_team - 1].name] += match.board_points[1]
        for cells in _rows(reference):
            if len(cells) == 16 and cells[0].isdigit():
                expected[cells[1]] = float(cells[13].replace(",", "."))
    else:
        totals = {str(player.number): 0.0 for player in tournament.players}
        for round_ in tournament.rounds:
            for game in round_.games:
                if game.points is not None:
                    totals[str(game.white_player)] += game.points[0]
                    if game.black_player > 0:
                        totals[str(game.black_player)] += game.points[1]
        rows = _rows(reference)
        header = next(cells for cells in rows if "SNo" in cells and "Pts." in cells)
        number_column, points_column = header.index("SNo"), header.index("Pts.")
        for cells in rows:
            if len(cells) == len(header) and cells[number_column].isdigit():
                # Do not drop rows for participants omitted from the ranking.
                expected[cells[number_column]] = float(cells[points_column].replace(",", "."))
    assert len(expected) == count
    assert totals == expected
