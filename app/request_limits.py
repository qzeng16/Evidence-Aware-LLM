"""Safe request boundaries for the verification API."""

from typing import Any, Dict, Optional, Tuple

from starlette.responses import JSONResponse

from app.config import load_app_config
from app.error_contract import (
    PAYLOAD_TOO_LARGE_ERROR,
    UNSUPPORTED_MEDIA_TYPE_ERROR,
    build_api_error_response,
)
from app.metrics import (
    record_verification_response,
)
from app.observability import (
    REQUEST_ID_HEADER,
    get_scope_request_id,
    normalize_request_id,
)
from app.services import (
    get_active_verifier_mode,
    get_configured_verifier_mode,
    is_llm_verifier_available,
)


def _header_value(
    scope: Dict[str, Any],
    header_name: str,
) -> Optional[str]:
    """Return one decoded ASGI request header."""

    expected_name = header_name.lower().encode(
        "latin-1"
    )

    for name, value in scope.get(
        "headers",
        [],
    ):
        if name.lower() == expected_name:
            return value.decode(
                "latin-1",
                errors="replace",
            )

    return None


def is_json_media_type(
    content_type: Optional[str],
) -> bool:
    """Return whether a media type represents JSON."""

    if content_type is None:
        return False

    media_type = content_type.split(
        ";",
        1,
    )[0].strip().lower()

    if media_type == "application/json":
        return True

    return (
        media_type.startswith(
            "application/"
        )
        and media_type.endswith(
            "+json"
        )
    )


def _safe_metadata() -> Dict[str, Any]:
    """Return non-secret verifier metadata."""

    return {
        "verifier_mode": (
            get_configured_verifier_mode()
        ),
        "active_verifier_mode": (
            get_active_verifier_mode()
        ),
        "llm_verifier_available": (
            is_llm_verifier_available()
        ),
    }


class RequestBoundaryMiddleware:
    """Enforce JSON and request-size limits for POST /verify."""

    def __init__(
        self,
        app: Any,
        max_request_body_bytes: Optional[int] = None,
    ) -> None:
        self.app = app

        configured_limit = (
            load_app_config()
            .max_request_body_bytes
        )

        self.max_request_body_bytes = int(
            configured_limit
            if max_request_body_bytes is None
            else max_request_body_bytes
        )

        if self.max_request_body_bytes <= 0:
            raise ValueError(
                "max_request_body_bytes must be "
                "greater than zero."
            )

    async def _reject(
        self,
        *,
        scope: Dict[str, Any],
        receive: Any,
        send: Any,
        status_code: int,
        error_type: str,
        message: str,
    ) -> None:
        """Return one safe request-boundary error."""

        request_id = (
            get_scope_request_id(scope)
            or normalize_request_id(None)
        )

        body = build_api_error_response(
            error_type=error_type,
            code=error_type,
            message=message,
            retryable=False,
            request_id=request_id,
            metadata=_safe_metadata(),
        )

        record_verification_response(
            body
        )

        response = JSONResponse(
            status_code=status_code,
            content=body,
            headers={
                REQUEST_ID_HEADER: request_id,
            },
        )

        await response(
            scope,
            receive,
            send,
        )

    async def _read_body(
        self,
        receive: Any,
    ) -> Tuple[bytes, bool]:
        """Read one bounded request body."""

        body = bytearray()

        while True:
            message = await receive()

            if message.get(
                "type"
            ) == "http.disconnect":
                return bytes(body), False

            if message.get(
                "type"
            ) != "http.request":
                continue

            chunk = message.get(
                "body",
                b"",
            )

            body.extend(chunk)

            if (
                len(body)
                > self.max_request_body_bytes
            ):
                return b"", True

            if not message.get(
                "more_body",
                False,
            ):
                return bytes(body), False

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Apply limits only to POST /verify."""

        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/verify"
        ):
            await self.app(
                scope,
                receive,
                send,
            )
            return

        content_type = _header_value(
            scope,
            "content-type",
        )

        if not is_json_media_type(
            content_type
        ):
            await self._reject(
                scope=scope,
                receive=receive,
                send=send,
                status_code=415,
                error_type=(
                    UNSUPPORTED_MEDIA_TYPE_ERROR
                ),
                message=(
                    "The /verify endpoint requires "
                    "a JSON request body."
                ),
            )
            return

        content_length = _header_value(
            scope,
            "content-length",
        )

        if content_length is not None:
            try:
                declared_length = int(
                    content_length
                )
            except ValueError:
                declared_length = 0

            if (
                declared_length
                > self.max_request_body_bytes
            ):
                await self._reject(
                    scope=scope,
                    receive=receive,
                    send=send,
                    status_code=413,
                    error_type=(
                        PAYLOAD_TOO_LARGE_ERROR
                    ),
                    message=(
                        "The request body exceeds "
                        "the maximum allowed size."
                    ),
                )
                return

        body, exceeded_limit = (
            await self._read_body(receive)
        )

        if exceeded_limit:
            await self._reject(
                scope=scope,
                receive=receive,
                send=send,
                status_code=413,
                error_type=(
                    PAYLOAD_TOO_LARGE_ERROR
                ),
                message=(
                    "The request body exceeds "
                    "the maximum allowed size."
                ),
            )
            return

        delivered = False

        async def replay_receive() -> Dict[str, Any]:
            nonlocal delivered

            if not delivered:
                delivered = True

                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }

            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }

        await self.app(
            scope,
            replay_receive,
            send,
        )
