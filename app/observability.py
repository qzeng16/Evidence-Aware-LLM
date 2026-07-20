"""Safe structured request logging and request tracing."""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from app.metrics import record_http_request
from app.services import get_active_verifier_mode


REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_LOGGER_NAME = "evidence_aware_llm.request"

REQUEST_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]{1,128}$"
)

REQUEST_LOGGER = logging.getLogger(
    REQUEST_LOGGER_NAME
)

REQUEST_LOGGER.setLevel(logging.INFO)
REQUEST_LOGGER.propagate = False


def _configure_request_logger() -> None:
    """Configure one JSON-lines stream handler."""

    for handler in REQUEST_LOGGER.handlers:
        if getattr(
            handler,
            "_evidence_json_handler",
            False,
        ):
            return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(message)s")
    )

    setattr(
        handler,
        "_evidence_json_handler",
        True,
    )

    REQUEST_LOGGER.addHandler(handler)


_configure_request_logger()


def normalize_request_id(
    value: Optional[str],
) -> str:
    """Return a safe caller ID or generate a new UUID."""

    if value is not None:
        normalized_value = value.strip()

        if REQUEST_ID_PATTERN.fullmatch(
            normalized_value
        ):
            return normalized_value

    return uuid4().hex


def get_scope_request_id(
    scope: Scope,
) -> Optional[str]:
    """Return the request ID stored in an ASGI scope."""

    state = scope.get("state")

    if not isinstance(state, dict):
        return None

    request_id = state.get("request_id")

    if not isinstance(request_id, str):
        return None

    return request_id


def _safe_active_verifier_mode() -> Optional[str]:
    """Read verifier mode without breaking request handling."""

    try:
        return get_active_verifier_mode()
    except Exception:
        return None


def emit_request_event(
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Write one machine-readable JSON log event."""

    payload: Dict[str, Any] = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event,
    }

    payload.update(fields)

    REQUEST_LOGGER.log(
        level,
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ),
    )


class RequestLoggingMiddleware:
    """Add request IDs and safe structured HTTP logs."""

    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        request_headers = Headers(
            scope=scope
        )

        request_id = normalize_request_id(
            request_headers.get(
                REQUEST_ID_HEADER
            )
        )

        state = scope.setdefault(
            "state",
            {},
        )

        state["request_id"] = request_id

        method = str(
            scope.get("method", "")
        )

        path = str(
            scope.get("path", "")
        )

        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(
            message: Message,
        ) -> None:
            nonlocal status_code

            if (
                message["type"]
                == "http.response.start"
            ):
                status_code = int(
                    message["status"]
                )

                response_headers = MutableHeaders(
                    scope=message
                )

                response_headers[
                    REQUEST_ID_HEADER
                ] = request_id

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_with_request_id,
            )
        except Exception as error:
            latency_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            record_http_request(
                method=method,
                path=path,
                status_code=500,
                latency_ms=latency_ms,
            )

            emit_request_event(
                "http_request_failed",
                level=logging.ERROR,
                request_id=request_id,
                method=method,
                path=path,
                status_code=500,
                latency_ms=latency_ms,
                active_verifier_mode=(
                    _safe_active_verifier_mode()
                ),
                exception_type=(
                    type(error).__name__
                ),
            )

            raise

        latency_ms = round(
            (
                time.perf_counter()
                - started_at
            )
            * 1000,
            3,
        )

        record_http_request(
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
        )

        emit_request_event(
            "http_request_completed",
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            active_verifier_mode=(
                _safe_active_verifier_mode()
            ),
        )
