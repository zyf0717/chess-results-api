"""Read Swiss-Manager tournament binaries as typed records."""

from ._binary import SwissManagerDecodeError
from .models import Tournament, TournamentType
from .swiss_manager import decode_tournament, load_tournament

__all__ = [
    "SwissManagerDecodeError",
    "Tournament",
    "TournamentType",
    "decode_tournament",
    "load_tournament",
]
