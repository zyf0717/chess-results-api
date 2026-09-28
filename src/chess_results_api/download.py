"""Optional browser-based retrieval of Swiss-Manager files from Chess-Results."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .swiss_manager import decode_tournament

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route


class TournamentDownloadError(Exception):
    """Tournament retrieval failed or returned a different tournament."""

    def __init__(
        self,
        message: str,
        *,
        reason: Literal["browser", "http", "unavailable", "id_mismatch"] | None = None,
        tournament_id: int | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.tournament_id = tournament_id
        self.http_status = http_status


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
    data = download_tournament_bytes(tournament_id, timeout=timeout, headless=headless)
    path = Path(destination)
    path.write_bytes(data)
    return path


def download_tournament_bytes(
    tournament_id: int,
    *,
    timeout: float = 30,
    headless: bool = True,
) -> bytes:
    """Return binary data after decoding and verifying the tournament ID.

    Requires the ``browser`` extra and Chromium. Timeout is in seconds per
    browser operation. Retrieval failures raise TournamentDownloadError;
    unsupported or malformed binaries raise SwissManagerDecodeError.
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
            with playwright.chromium.launch(
                headless=headless, timeout=timeout * 1000
            ) as browser:
                with browser.new_context(
                    accept_downloads=True, service_workers="block"
                ) as context:
                    context.set_default_timeout(timeout * 1000)
                    context.route("**/*", _filter_requests)
                    data = _download(context.new_page(), tournament_id)
    except Error as exc:
        raise TournamentDownloadError(
            f"Could not download tournament {tournament_id}: {exc}",
            reason="browser",
            tournament_id=tournament_id,
        ) from exc

    tournament = decode_tournament(data)
    if tournament.tournament_id != tournament_id:
        raise TournamentDownloadError(
            f"Requested tournament {tournament_id}, "
            f"received {tournament.tournament_id}",
            reason="id_mismatch",
            tournament_id=tournament_id,
        )
    return data


def _filter_requests(route: Route) -> None:
    if route.request.resource_type in {"image", "font", "media"}:
        route.abort("blockedbyclient")
    else:
        route.fallback()


def _download(page: Page, tournament_id: int) -> bytes:
    # The download URL has no tournament ID: navigation establishes the session.
    response = page.goto(
        f"https://s1.chess-results.com/tnr{tournament_id}.aspx?lan=1&turdet=YES",
        wait_until="domcontentloaded",
    )
    if response is None or not response.ok:
        status = response.status if response is not None else None
        raise TournamentDownloadError(
            f"Tournament {tournament_id}: "
            f"HTTP {status if status is not None else 'no response'}",
            reason="http",
            tournament_id=tournament_id,
            http_status=status,
        )

    details = page.locator("#cb_alleDetails")
    if details.count():
        details.click()
        page.wait_for_load_state("domcontentloaded")

    link = page.get_by_role("link", name="Swiss-Manager tournamentfile", exact=True)
    if not link.count():
        raise TournamentDownloadError(
            f"Tournament {tournament_id} has no Swiss-Manager tournamentfile link",
            reason="unavailable",
            tournament_id=tournament_id,
        )
    with page.expect_download() as pending:
        link.click()
    # Read before closing the context, which deletes its temporary downloads.
    return pending.value.path().read_bytes()
