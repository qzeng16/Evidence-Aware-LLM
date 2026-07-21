"""Tests for HTTP security headers and browser CSP."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes as routes
from app.exception_handlers import (
    register_exception_handlers,
)
from app.observability import (
    RequestLoggingMiddleware,
)
from app.request_limits import (
    RequestBoundaryMiddleware,
)
from app.security_headers import (
    DEMO_CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)
from app.static_routes import (
    router as static_router,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

EXPECTED_PERMISSIONS_POLICY = (
    "camera=(), microphone=(), "
    "geolocation=(), payment=(), usb=()"
)


def build_client() -> TestClient:
    """Build an app with the production middleware order."""

    test_app = FastAPI()

    test_app.add_middleware(
        RequestBoundaryMiddleware,
        max_request_body_bytes=4096,
    )

    test_app.add_middleware(
        RequestLoggingMiddleware
    )

    test_app.add_middleware(
        SecurityHeadersMiddleware
    )

    register_exception_handlers(
        test_app
    )

    test_app.include_router(
        static_router
    )

    test_app.include_router(
        routes.router
    )

    return TestClient(
        test_app,
        raise_server_exceptions=False,
    )


def assert_common_security_headers(
    response,
) -> None:
    """Validate headers shared by all HTTP responses."""

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        response.headers[
            "x-frame-options"
        ]
        == "DENY"
    )

    assert (
        response.headers[
            "referrer-policy"
        ]
        == "no-referrer"
    )

    assert (
        response.headers[
            "permissions-policy"
        ]
        == EXPECTED_PERMISSIONS_POLICY
    )


def test_demo_uses_strict_csp_and_external_assets():
    client = build_client()

    response = client.get(
        "/",
        headers={
            "Accept": "text/html",
        },
    )

    assert response.status_code == 200
    assert_common_security_headers(response)

    assert (
        response.headers[
            "content-security-policy"
        ]
        == DEMO_CONTENT_SECURITY_POLICY
    )

    assert (
        "'unsafe-inline'"
        not in response.headers[
            "content-security-policy"
        ]
    )

    assert (
        response.headers["cache-control"]
        == "no-store"
    )

    assert (
        'href="/assets/demo.css"'
        in response.text
    )

    assert (
        'src="/assets/demo.js"'
        in response.text
    )

    assert "<style>" not in response.text
    assert "<script>" not in response.text


def test_demo_assets_are_same_origin_and_cacheable():
    client = build_client()

    stylesheet = client.get(
        "/assets/demo.css"
    )

    javascript = client.get(
        "/assets/demo.js"
    )

    assert stylesheet.status_code == 200
    assert javascript.status_code == 200

    assert_common_security_headers(
        stylesheet
    )

    assert_common_security_headers(
        javascript
    )

    assert stylesheet.headers[
        "content-type"
    ].startswith(
        "text/css"
    )

    assert javascript.headers[
        "content-type"
    ].startswith(
        "application/javascript"
    )

    assert (
        stylesheet.headers["cache-control"]
        == "public, max-age=3600"
    )

    assert (
        javascript.headers["cache-control"]
        == "public, max-age=3600"
    )

    assert ":root" in stylesheet.text

    assert (
        'requestJson("/health"'
        in javascript.text
    )

    assert (
        'requestJson("/verify"'
        in javascript.text
    )


def test_api_and_metrics_responses_use_no_store():
    client = build_client()

    responses = (
        client.get(
            "/",
            headers={
                "Accept": "application/json",
            },
        ),
        client.get("/live"),
        client.get("/metrics"),
    )

    for response in responses:
        assert response.status_code == 200
        assert_common_security_headers(
            response
        )

        assert (
            response.headers["cache-control"]
            == "no-store"
        )


def test_error_responses_keep_security_headers():
    client = build_client()

    responses = (
        client.get(
            "/does-not-exist"
        ),
        client.post(
            "/verify",
            content="not-json",
            headers={
                "Content-Type": "text/plain",
            },
        ),
        client.post(
            "/verify",
            content='{"claim": ',
            headers={
                "Content-Type": (
                    "application/json"
                ),
            },
        ),
    )

    assert [
        response.status_code
        for response in responses
    ] == [
        404,
        415,
        422,
    ]

    for response in responses:
        assert_common_security_headers(
            response
        )

        assert (
            response.headers["cache-control"]
            == "no-store"
        )


def test_docs_remain_available_without_demo_csp():
    client = build_client()

    response = client.get(
        "/docs"
    )

    assert response.status_code == 200
    assert_common_security_headers(response)

    assert (
        response.headers["cache-control"]
        == "no-store"
    )

    assert (
        "content-security-policy"
        not in response.headers
    )

    assert "Swagger UI" in response.text


def test_security_middleware_is_outermost():
    main_text = (
        PROJECT_ROOT
        / "app"
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    boundary_index = main_text.index(
        (
            "app.add_middleware(\n"
            "    RequestBoundaryMiddleware"
        )
    )

    logging_index = main_text.index(
        (
            "app.add_middleware(\n"
            "    RequestLoggingMiddleware"
        )
    )

    security_index = main_text.index(
        (
            "app.add_middleware(\n"
            "    SecurityHeadersMiddleware"
        )
    )

    assert (
        boundary_index
        < logging_index
        < security_index
    )
