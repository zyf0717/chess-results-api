"""Optional browser-based retrieval of Swiss-Manager files from Chess-Results."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING

from .swiss_manager import decode_tournament

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TournamentDownloadError(Exception):
    """Tournament retrieval failed or returned a different tournament."""


def download_tournament(
    tournament_id: int,
    destination: str | Path,
    *,
    timeout: float = 30,
    headless: bool = True,
) -> Path:
    """Download and validate a tournament file using an isolated Chromium session.

    Requires the ``browser`` extra and ``playwright install chromium``. Timeout
    is in seconds per browser operation. The destination's parent must exist;
    an existing file is replaced only after decoding and verifying the ID.

    Browser failures raise TournamentDownloadError, unsupported or malformed
    binaries raise SwissManagerDecodeError, and filesystem errors propagate.
    """
    if isinstance(tournament_id, bool) or not isinstance(tournament_id, int):
        raise ValueError("tournament_id must be a positive integer")
    if tournament_id <= 0:
        raise ValueError("tournament_id must be a positive integer")
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")

    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Install chess-results-api[browser] and run playwright install chromium"
        ) from exc

    try:
        with sync_playwright() as playwright:
            with playwright.chromium.launch(headless=headless, timeout=timeout * 1000) as browser:
                with browser.new_context(accept_downloads=True) as context:
                    context.set_default_timeout(timeout * 1000)
                    data = _download(context.new_page(), tournament_id)
    except Error as exc:
        raise TournamentDownloadError(
            f"Could not download tournament {tournament_id}: {exc}"
        ) from exc

    tournament = decode_tournament(data)
    if tournament.tournament_id != tournament_id:
        raise TournamentDownloadError(
            f"Requested tournament {tournament_id}, received {tournament.tournament_id}"
        )
    path = Path(destination)
    path.write_bytes(data)
    return path


def _download(page: Page, tournament_id: int) -> bytes:
    # The download URL has no tournament ID: navigation establishes the session.
    response = page.goto(
        f"https://s1.chess-results.com/tnr{tournament_id}.aspx?lan=1&turdet=YES",
        wait_until="domcontentloaded",
    )
    if response is None or not response.ok:
        status = response.status if response else "no response"
        raise TournamentDownloadError(f"Tournament {tournament_id}: HTTP {status}")

    details = page.locator("#cb_alleDetails")
    if details.count():
        details.click()
        page.wait_for_load_state("domcontentloaded")

    link = page.get_by_role("link", name="Swiss-Manager tournamentfile", exact=True)
    if not link.count():
        raise TournamentDownloadError(
            f"Tournament {tournament_id} has no Swiss-Manager tournamentfile link"
        )
    with page.expect_download() as pending:
        link.click()
    # Read before closing the context, which deletes its temporary downloads.
    return pending.value.path().read_bytes()
