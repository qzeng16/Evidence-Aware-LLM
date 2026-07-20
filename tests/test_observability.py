"""Tests for safe request tracing and JSON logs."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Tuple

import pytest

from app.observability import (
    REQUEST_ID_HEADER,
    REQUEST_LOGGER,
    RequestLoggingMiddleware,
)


REQUEST_ID_REGEX = re.compile(
    r"^[a-f0-9]{32}$"
)


def make_scope(
    *,
    path: str = "/probe",
    method: str = "POST",
    headers: List[
        Tuple[bytes, bytes]
    ] = None,
) -> Dict[str, Any]:
    """Create a minimal HTTP ASGI scope."""

    return {
        "type": "http",
        "asgi": {
            "version": "3.0",
        },
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "client": (
            "127.0.0.1",
            50000,
        ),
        "server": (
            "testserver",
            80,
        ),
    }


def run_http_app(
    app: Any,
    scope: Dict[str, Any],
    *,
    body: bytes = b"",
) -> List[Dict[str, Any]]:
    """Run one ASGI request and collect messages."""

    messages: List[
        Dict[str, Any]
    ] = []

    async def receive() -> Dict[str, Any]:
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    async def send(
        message: Dict[str, Any],
    ) -> None:
        messages.append(message)

    asyncio.run(
        app(
            scope,
            receive,
            send,
        )
    )

    return messages


async def successful_app(
    scope: Dict[str, Any],
    receive: Any,
    send: Any,
) -> None:
    """Return a successful empty JSON response."""

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (
                    b"content-type",
                    b"application/json",
                )
            ],
        }
    )

    await send(
        {
            "type": "http.response.body",
            "body": b"{}",
            "more_body": False,
        }
    )


async def failing_app(
    scope: Dict[str, Any],
    receive: Any,
    send: Any,
) -> None:
    """Raise an error containing sensitive sample text."""

    raise RuntimeError(
        "sensitive-claim-value "
        "OPENAI_API_KEY=sk-proj-secret"
    )


def parse_request_events(
    caplog: Any,
) -> List[Dict[str, Any]]:
    """Parse JSON request events from captured logs."""

    events = []

    for record in caplog.records:
        try:
            payload = json.loads(
                record.getMessage()
            )
        except json.JSONDecodeError:
            continue

        if str(
            payload.get("event", "")
        ).startswith("http_request_"):
            events.append(payload)

    return events


def attach_capture_handler(
    caplog: Any,
) -> None:
    """Attach pytest's log handler to the isolated logger."""

    if caplog.handler not in (
        REQUEST_LOGGER.handlers
    ):
        REQUEST_LOGGER.addHandler(
            caplog.handler
        )


def detach_capture_handler(
    caplog: Any,
) -> None:
    """Remove pytest's log handler."""

    if caplog.handler in (
        REQUEST_LOGGER.handlers
    ):
        REQUEST_LOGGER.removeHandler(
            caplog.handler
        )


def response_headers(
    messages: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Return decoded response headers."""

    start_message = next(
        message
        for message in messages
        if (
            message["type"]
            == "http.response.start"
        )
    )

    return {
        key.decode("latin-1").lower():
        value.decode("latin-1")
        for key, value
        in start_message["headers"]
    }


def test_generated_request_id_is_returned_and_logged(
    caplog: Any,
) -> None:
    """Requests without IDs should receive a generated UUID."""

    caplog.clear()
    attach_capture_handler(caplog)

    try:
        middleware = RequestLoggingMiddleware(
            successful_app
        )

        scope = make_scope()

        messages = run_http_app(
            middleware,
            scope,
        )
    finally:
        detach_capture_handler(caplog)

    request_id = response_headers(
        messages
    )[REQUEST_ID_HEADER.lower()]

    assert REQUEST_ID_REGEX.fullmatch(
        request_id
    )

    assert (
        scope["state"]["request_id"]
        == request_id
    )

    events = parse_request_events(
        caplog
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event["event"]
        == "http_request_completed"
    )
    assert event["request_id"] == request_id
    assert event["method"] == "POST"
    assert event["path"] == "/probe"
    assert event["status_code"] == 200
    assert event["latency_ms"] >= 0
    assert "active_verifier_mode" in event


def test_valid_caller_request_id_is_preserved(
    caplog: Any,
) -> None:
    """A safe caller-provided request ID should be reused."""

    caplog.clear()
    attach_capture_handler(caplog)

    supplied_id = (
        "client-request_2026-07-20"
    )

    try:
        middleware = RequestLoggingMiddleware(
            successful_app
        )

        messages = run_http_app(
            middleware,
            make_scope(
                headers=[
                    (
                        b"x-request-id",
                        supplied_id.encode(
                            "utf-8"
                        ),
                    )
                ]
            ),
        )
    finally:
        detach_capture_handler(caplog)

    assert response_headers(
        messages
    )[REQUEST_ID_HEADER.lower()] == supplied_id

    events = parse_request_events(
        caplog
    )

    assert events[0][
        "request_id"
    ] == supplied_id


def test_invalid_request_id_is_replaced(
    caplog: Any,
) -> None:
    """Unsafe request IDs must not reach logs or responses."""

    caplog.clear()
    attach_capture_handler(caplog)

    invalid_id = (
        "invalid request\ninjected-log-line"
    )

    try:
        middleware = RequestLoggingMiddleware(
            successful_app
        )

        messages = run_http_app(
            middleware,
            make_scope(
                headers=[
                    (
                        b"x-request-id",
                        invalid_id.encode(
                            "utf-8"
                        ),
                    )
                ]
            ),
        )
    finally:
        detach_capture_handler(caplog)

    generated_id = response_headers(
        messages
    )[REQUEST_ID_HEADER.lower()]

    assert generated_id != invalid_id
    assert REQUEST_ID_REGEX.fullmatch(
        generated_id
    )

    serialized_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
    )

    assert invalid_id not in serialized_logs


def test_request_body_and_credentials_are_not_logged(
    caplog: Any,
) -> None:
    """Claim contents and credential patterns must stay private."""

    caplog.clear()
    attach_capture_handler(caplog)

    sensitive_body = (
        b'{"claim":"private-claim-value",'
        b'"token":"hf_private_token"}'
    )

    try:
        middleware = RequestLoggingMiddleware(
            successful_app
        )

        run_http_app(
            middleware,
            make_scope(),
            body=sensitive_body,
        )
    finally:
        detach_capture_handler(caplog)

    serialized_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
    )

    assert "private-claim-value" not in (
        serialized_logs
    )
    assert "hf_private_token" not in (
        serialized_logs
    )
    assert "claim" not in serialized_logs


def test_failure_log_excludes_exception_message(
    caplog: Any,
) -> None:
    """Failure logs should contain type, not sensitive details."""

    caplog.clear()
    attach_capture_handler(caplog)

    middleware = RequestLoggingMiddleware(
        failing_app
    )

    try:
        with pytest.raises(
            RuntimeError
        ):
            run_http_app(
                middleware,
                make_scope(
                    path="/failure",
                    method="GET",
                ),
            )
    finally:
        detach_capture_handler(caplog)

    events = parse_request_events(
        caplog
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event["event"]
        == "http_request_failed"
    )
    assert event["status_code"] == 500
    assert (
        event["exception_type"]
        == "RuntimeError"
    )

    serialized_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
    )

    assert "sensitive-claim-value" not in (
        serialized_logs
    )
    assert "sk-proj-secret" not in (
        serialized_logs
    )
    assert "OPENAI_API_KEY" not in (
        serialized_logs
    )
