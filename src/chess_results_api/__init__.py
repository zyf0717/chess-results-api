"""Retrieve Chess-Results tournament files and decode their typed records."""

from ._binary import SwissManagerDecodeError
from .download import (
    TournamentDownloadError,
    download_tournament,
    download_tournament_bytes,
)
from .models import Tournament, TournamentType
from .swiss_manager import decode_tournament, load_tournament

__all__ = [
    "SwissManagerDecodeError",
    "Tournament",
    "TournamentDownloadError",
    "TournamentType",
    "decode_tournament",
    "download_tournament",
    "download_tournament_bytes",
    "load_tournament",
]
