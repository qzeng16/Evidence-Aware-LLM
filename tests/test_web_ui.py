"""Tests for browser and API behavior at the root endpoint."""

from typing import Dict

from fastapi.responses import HTMLResponse
from starlette.requests import Request

from app.routes import root


def make_request(
    accept: str,
) -> Request:
    """Create a minimal request with a controlled Accept header."""

    scope: Dict[str, object] = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (
                b"accept",
                accept.encode("utf-8"),
            )
        ],
        "client": ("test-client", 50000),
        "server": ("test-server", 80),
    }

    return Request(scope)


def test_root_serves_demo_to_browser() -> None:
    """Browsers should receive the interactive HTML interface."""

    response = root(
        make_request("text/html,application/xhtml+xml")
    )

    assert isinstance(response, HTMLResponse)

    html = response.body.decode("utf-8")

    assert "Evidence-Aware Claim Verification" in html
    assert 'id="verify-form"' in html
    assert (
        'href="/assets/demo.css"'
        in html
    )
    assert (
        'src="/assets/demo.js"'
        in html
    )
    assert "<style>" not in html
    assert "<script>" not in html


def test_root_preserves_json_navigation() -> None:
    """Non-browser clients should retain the existing JSON response."""

    response = root(
        make_request("application/json")
    )

    assert isinstance(response, dict)
    assert response["docs"] == "/docs"
    assert response["health_endpoint"] == "/health"
    assert response["verify_endpoint"] == "/verify"


def test_demo_does_not_embed_credentials() -> None:
    """The public page must not contain credential-like values."""

    response = root(
        make_request("text/html")
    )

    assert isinstance(response, HTMLResponse)

    html = response.body.decode("utf-8")

    assert "OPENAI_API_KEY" not in html
    assert "sk-proj-" not in html
    assert "hf_" not in html
