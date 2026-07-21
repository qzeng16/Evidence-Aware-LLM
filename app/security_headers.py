"""Global HTTP security and cache-control headers."""

from typing import Any, Dict

from starlette.datastructures import MutableHeaders


DEMO_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'"
)

COMMON_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "camera=(), microphone=(), "
        "geolocation=(), payment=(), usb=()"
    ),
}

DYNAMIC_CACHE_CONTROL = (
    "no-store"
)

STATIC_CACHE_CONTROL = (
    "public, max-age=3600"
)


class SecurityHeadersMiddleware:
    """Apply security headers to successful and error responses."""

    def __init__(
        self,
        app: Any,
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Attach headers to every HTTP response."""

        if scope.get("type") != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        path = str(
            scope.get(
                "path",
                "",
            )
        )

        async def send_with_headers(
            message: Dict[str, Any],
        ) -> None:
            if (
                message.get("type")
                == "http.response.start"
            ):
                headers = MutableHeaders(
                    scope=message
                )

                for (
                    header_name,
                    header_value,
                ) in COMMON_SECURITY_HEADERS.items():
                    headers[
                        header_name
                    ] = header_value

                if path.startswith(
                    "/assets/"
                ):
                    headers[
                        "Cache-Control"
                    ] = STATIC_CACHE_CONTROL
                else:
                    headers[
                        "Cache-Control"
                    ] = DYNAMIC_CACHE_CONTROL

                content_type = headers.get(
                    "Content-Type",
                    "",
                ).lower()

                if (
                    path == "/"
                    and content_type.startswith(
                        "text/html"
                    )
                ):
                    headers[
                        "Content-Security-Policy"
                    ] = (
                        DEMO_CONTENT_SECURITY_POLICY
                    )

            await send(message)

        await self.app(
            scope,
            receive,
            send_with_headers,
        )
