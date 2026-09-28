"""Retrieve Chess-Results tournament files and decode their typed records."""

from ._binary import SwissManagerDecodeError
from .download import TournamentDownloadError, download_tournament
from .models import Tournament, TournamentType
from .swiss_manager import decode_tournament, load_tournament

__all__ = [
    "SwissManagerDecodeError",
    "Tournament",
    "TournamentDownloadError",
    "TournamentType",
    "decode_tournament",
    "download_tournament",
    "load_tournament",
]
