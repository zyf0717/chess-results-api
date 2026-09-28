"""Offline browser navigation and download validation against synthetic responses."""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from chess_results_api import (
    SwissManagerDecodeError,
    TournamentDownloadError,
    decode_tournament,
    download_tournament,
    download_tournament_bytes,
    load_tournament,
)

from .helpers import _document


@pytest.fixture
def serve(monkeypatch):
    """Route every browser request locally, including the session-dependent download."""
    api = pytest.importorskip("playwright.sync_api", reason="Install the browser extra")
    with api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Run playwright install chromium for offline browser tests")
    new_context = api.Browser.new_context

    def setup(
        *,
        payload=None,
        details=True,
        link=True,
        status=200,
        network_error=False,
        assets=False,
        download=True,
    ):
        requests = []
        data = _document() if payload is None else payload

        def respond(route):
            request = route.request
            requests.append(request)
            if network_error:
                route.abort("failed")
                return
            url = urlsplit(request.url)
            if url.path == "/required.js":
                route.fulfill(
                    content_type="application/javascript",
                    body="""
                        const image = new Image();
                        const imageDone = new Promise(resolve => {
                            image.onerror = resolve;
                        });
                        image.src = '/decoration.png';
                        const font = new FontFace(
                            'Decoration', 'url(/decoration.woff2)'
                        );
                        const media = document.createElement('video');
                        const mediaDone = new Promise(resolve => {
                            media.onerror = resolve;
                        });
                        media.src = '/decoration.mp4';
                        media.load();
                        Promise.allSettled([
                            imageDone, font.load(), mediaDone, fetch('/state')
                        ])
                            .then(() => {
                                const button = document.getElementById(
                                    'cb_alleDetails'
                                );
                                button.disabled = false;
                            });
                    """,
                )
                return
            if url.path == "/state":
                route.fulfill(json={"ready": True})
                return
            if url.path.lower() == "/downloadturnier.aspx":
                assert "tournament=12345" in request.headers.get("cookie", "")
                if not download:
                    route.fulfill(content_type="text/html", body="No download")
                    return
                route.fulfill(
                    body=data,
                    content_type="application/octet-stream",
                    headers={
                        "Content-Disposition": 'attachment; filename="event.TUMX"'
                    },
                )
                return
            if url.path != "/tnr12345.aspx":
                route.abort()
                return
            assert parse_qs(url.query) == {"lan": ["1"], "turdet": ["YES"]}
            if request.method == "GET":
                assert "tournament=" not in request.headers.get("cookie", "")
            if details and request.method == "GET":
                body = """<form method="post">
                    <input type="hidden" name="__VIEWSTATE" value="synthetic-state">
                    <input type="submit" id="cb_alleDetails" name="cb_alleDetails"
                           value="Show tournament details">
                </form>"""
                if assets:
                    body = body.replace('type="submit"', 'type="submit" disabled')
                    body += '<script src="/required.js"></script>'
            else:
                if details:
                    assert request.method == "POST"
                    assert parse_qs(request.post_data) == {
                        "__VIEWSTATE": ["synthetic-state"],
                        "cb_alleDetails": ["Show tournament details"],
                    }
                body = (
                    '<a href="/DownloadTurnier.Aspx?art=1">'
                    "Swiss-Manager tournamentfile</a>"
                    if link
                    else "No file available"
                )
            route.fulfill(
                status=status,
                content_type="text/html",
                body=body,
                headers={"Set-Cookie": "tournament=12345; Path=/; Secure"},
            )

        def context_with_routes(browser, **kwargs):
            context = new_context(browser, **kwargs)
            context.route("**/*", respond)
            return context

        monkeypatch.setattr(api.Browser, "new_context", context_with_routes)
        return requests

    return setup


@pytest.mark.parametrize("details", [False, True])
def test_download_preserves_session_and_form_state(
    serve, tmp_path: Path, details: bool
) -> None:
    requests = serve(details=details)
    path = tmp_path / "event.TUMX"
    assert download_tournament(12345, path) == path
    assert path.read_bytes() == _document()
    assert load_tournament(path).tournament_id == 12345
    assert [request.method for request in requests] == (
        ["GET", "POST", "GET"] if details else ["GET", "GET"]
    )


def test_downloads_use_separate_sessions(serve, tmp_path: Path) -> None:
    requests = serve()
    for name in ("first", "second"):
        download_tournament(12345, tmp_path / name)
    assert (
        len(requests) == 6
    )  # The route also checks each initial request has no cookie.


@pytest.mark.parametrize("details", [False, True])
def test_download_bytes(serve, details: bool) -> None:
    serve(details=details)
    data = download_tournament_bytes(12345)
    assert data == _document()
    assert decode_tournament(data).tournament_id == 12345


def test_blocks_visual_resources_but_preserves_navigation_scripts(
    serve, tmp_path: Path
) -> None:
    requests = serve(assets=True)
    path = download_tournament(12345, tmp_path / "event")
    assert path.read_bytes() == _document()
    # Blocked requests must never reach the simulated server. The form stays
    # disabled until the script runs and all three resource requests settle.
    assert [urlsplit(request.url).path for request in requests] == [
        "/tnr12345.aspx",
        "/required.js",
        "/state",
        "/tnr12345.aspx",
        "/DownloadTurnier.Aspx",
    ]


def test_browser_failure(serve, tmp_path: Path) -> None:
    serve(network_error=True)
    path = tmp_path / "event"
    with pytest.raises(
        TournamentDownloadError, match="Could not download tournament 12345"
    ) as caught:
        download_tournament(12345, path)
    assert caught.value.reason == "browser"
    assert caught.value.tournament_id == 12345
    assert caught.value.http_status is None
    assert caught.value.__cause__ is not None
    assert not path.exists()


def test_download_timeout(serve) -> None:
    from playwright.sync_api import TimeoutError

    serve(download=False)
    with pytest.raises(TournamentDownloadError) as caught:
        download_tournament_bytes(12345, timeout=1)
    assert caught.value.reason == "browser"
    assert caught.value.tournament_id == 12345
    assert isinstance(caught.value.__cause__, TimeoutError)


@pytest.mark.parametrize(
    "status,link,message,reason",
    [(503, True, "HTTP 503", "http"), (200, False, "no Swiss", "unavailable")],
)
def test_unavailable_download_preserves_destination(
    serve, tmp_path: Path, status: int, link: bool, message: str, reason: str
) -> None:
    serve(status=status, link=link)
    path = tmp_path / "existing"
    path.write_bytes(b"existing content")
    with pytest.raises(TournamentDownloadError, match=message) as caught:
        download_tournament(12345, path)
    assert caught.value.reason == reason
    assert caught.value.tournament_id == 12345
    assert caught.value.http_status == (status if reason == "http" else None)
    assert path.read_bytes() == b"existing content"


@pytest.mark.parametrize(
    "payload,error",
    [
        (b"<html>Error</html>", SwissManagerDecodeError),
        (
            _document().replace(
                (12345).to_bytes(4, "little"), (54321).to_bytes(4, "little"), 1
            ),
            TournamentDownloadError,
        ),
    ],
)
@pytest.mark.parametrize("in_memory", [False, True])
def test_rejects_invalid_or_wrong_tournament(
    serve, tmp_path: Path, payload: bytes, error: type[Exception], in_memory: bool
) -> None:
    serve(payload=payload)
    path = tmp_path / "event"
    path.write_bytes(b"existing content")
    with pytest.raises(error) as caught:
        if in_memory:
            download_tournament_bytes(12345)
        else:
            download_tournament(12345, path)
    if error is TournamentDownloadError:
        assert caught.value.reason == "id_mismatch"
        assert caught.value.tournament_id == 12345
        assert caught.value.http_status is None
        assert "received 54321" in str(caught.value)
    assert path.read_bytes() == b"existing content"


def test_filesystem_error_propagates(serve, tmp_path: Path) -> None:
    serve()
    with pytest.raises(FileNotFoundError):
        download_tournament(12345, tmp_path / "missing" / "event")


@pytest.mark.parametrize("tournament_id", [0, -1, True, "12345", 1.5])
def test_invalid_tournament_id(tmp_path: Path, tournament_id) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        download_tournament(tournament_id, tmp_path / "event")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        download_tournament(12345, tmp_path / "event", timeout=timeout)


def test_missing_browser_extra(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(ImportError, match=r"chess-results-api\[browser\]"):
        download_tournament(12345, tmp_path / "event")
