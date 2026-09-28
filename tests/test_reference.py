"""Independent, offline comparison against an optional published HTML snapshot."""

import re
from html import unescape
from pathlib import Path

import pytest

from chess_results_api.tumx import load_tumx


def test_local_published_board_point_totals() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    source = fixtures / "olympiad2026open_1469895.TUMX"
    reference = fixtures / "standings-reference.html"
    if not source.is_file() or not reference.is_file():
        pytest.skip("Optional local tournament and published standings snapshot are required")
    tournament = load_tumx(source)
    totals = {team.number: 0.0 for team in tournament.teams}
    for round_ in tournament.rounds:
        for match in round_.matches:
            assert match.board_points is not None
            totals[match.first_team] += match.board_points[0]
            if match.second_team > 0:
                totals[match.second_team] += match.board_points[1]

    # This is a fixed reference snapshot, not a general Chess-Results HTML client.
    expected = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", reference.read_text("utf-8-sig"), re.S):
        cells = [
            " ".join(unescape(re.sub("<[^>]*>", " ", cell)).split())
            for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)
        ]
        if len(cells) == 14 and cells[0].isdigit() and cells[1].isdigit():
            number = int(cells[1])
            assert number not in expected
            expected[number] = float(cells[-2].replace(",", "."))
    assert len(expected) == 206
    assert totals == expected
