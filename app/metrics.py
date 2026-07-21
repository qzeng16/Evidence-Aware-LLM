"""Low-cardinality Prometheus application metrics."""

from typing import Any, Dict, Tuple

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


METRICS_REGISTRY = CollectorRegistry(
    auto_describe=True
)

KNOWN_HTTP_PATHS = {
    "/",
    "/docs",
    "/health",
    "/live",
    "/ready",
    "/metrics",
    "/openapi.json",
    "/redoc",
    "/verify",
}

HTTP_REQUESTS_TOTAL = Counter(
    "evidence_http_requests_total",
    "Total HTTP requests handled by the API.",
    (
        "method",
        "path",
        "status_code",
    ),
    registry=METRICS_REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "evidence_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    (
        "method",
        "path",
    ),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
    registry=METRICS_REGISTRY,
)

VERIFICATION_REQUESTS_TOTAL = Counter(
    "evidence_verification_requests_total",
    "Total claim verification requests by outcome.",
    ("outcome",),
    registry=METRICS_REGISTRY,
)

VERIFICATION_ERRORS_TOTAL = Counter(
    "evidence_verification_errors_total",
    "Total verification failures by stable error type.",
    ("error_type",),
    registry=METRICS_REGISTRY,
)


VERIFICATION_IN_FLIGHT = Gauge(
    "evidence_verification_in_flight",
    "Verification requests currently executing.",
    registry=METRICS_REGISTRY,
)

VERIFICATION_REJECTED_TOTAL = Counter(
    "evidence_verification_rejected_total",
    "Verification requests rejected due to saturation.",
    registry=METRICS_REGISTRY,
)

VERIFICATION_QUEUE_WAIT_SECONDS = Histogram(
    "evidence_verification_queue_wait_seconds",
    "Time spent waiting for a verification execution slot.",
    buckets=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
    ),
    registry=METRICS_REGISTRY,
)


VERIFICATION_RESULTS_TOTAL = Counter(
    "evidence_verification_results_total",
    "Total verification results by label and verifier.",
    (
        "label",
        "verifier_type",
    ),
    registry=METRICS_REGISTRY,
)

VERIFICATION_CONFIDENCE = Histogram(
    "evidence_verification_confidence",
    "Distribution of successful verification confidence.",
    (
        "label",
        "verifier_type",
    ),
    buckets=(
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
    registry=METRICS_REGISTRY,
)


def record_verification_queue_wait(
    wait_seconds: float,
) -> None:
    """Record time spent waiting for an execution slot."""

    VERIFICATION_QUEUE_WAIT_SECONDS.observe(
        max(float(wait_seconds), 0.0)
    )


def record_verification_started() -> None:
    """Increment the number of executing verifications."""

    VERIFICATION_IN_FLIGHT.inc()


def record_verification_finished() -> None:
    """Decrement the number of executing verifications."""

    VERIFICATION_IN_FLIGHT.dec()


def record_verification_rejected() -> None:
    """Record one request rejected due to saturation."""

    VERIFICATION_REJECTED_TOTAL.inc()


def normalize_metric_path(
    path: str,
) -> str:
    """Limit path labels to a fixed low-cardinality set."""

    if path in KNOWN_HTTP_PATHS:
        return path

    return "/other"


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
) -> None:
    """Record one completed HTTP request."""

    normalized_method = (
        method.strip().upper()
        if method.strip()
        else "UNKNOWN"
    )

    normalized_path = normalize_metric_path(
        path
    )

    HTTP_REQUESTS_TOTAL.labels(
        method=normalized_method,
        path=normalized_path,
        status_code=str(status_code),
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=normalized_method,
        path=normalized_path,
    ).observe(
        max(float(latency_ms), 0.0)
        / 1000.0
    )


def normalize_confidence(
    value: Any,
) -> float:
    """Normalize a confidence value to the range zero to one."""

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if confidence > 1.0:
        confidence /= 100.0

    return max(
        0.0,
        min(1.0, confidence),
    )


def record_verification_response(
    response: Dict[str, Any],
) -> None:
    """Record safe aggregate information from a verification response."""

    outcome = (
        "success"
        if response.get("status") == "success"
        else "error"
    )

    VERIFICATION_REQUESTS_TOTAL.labels(
        outcome=outcome
    ).inc()

    if outcome != "success":
        error = response.get("error")

        error_type = (
            error.get("type")
            if isinstance(error, dict)
            else None
        )

        allowed_error_types = {
            "invalid_claim",
            "invalid_request",
            "service_unavailable",
            "service_overloaded",
            "payload_too_large",
            "unsupported_media_type",
            "provider_error",
            "internal_error",
        }

        if error_type not in allowed_error_types:
            error_type = "unknown"

        VERIFICATION_ERRORS_TOTAL.labels(
            error_type=error_type
        ).inc()

        return

    data = response.get("data")

    if not isinstance(data, dict):
        return

    verification = data.get(
        "verification"
    )

    if not isinstance(
        verification,
        dict,
    ):
        return

    label = str(
        verification.get(
            "label",
            "Unknown",
        )
    )

    if label not in {
        "Supported",
        "Refuted",
        "Uncertain",
    }:
        label = "Unknown"

    verifier_type = str(
        verification.get(
            "verifier_type",
            "unknown",
        )
    ).lower()

    if verifier_type not in {
        "rule",
        "llm",
        "hybrid",
    }:
        verifier_type = "unknown"

    VERIFICATION_RESULTS_TOTAL.labels(
        label=label,
        verifier_type=verifier_type,
    ).inc()

    VERIFICATION_CONFIDENCE.labels(
        label=label,
        verifier_type=verifier_type,
    ).observe(
        normalize_confidence(
            verification.get(
                "confidence"
            )
        )
    )


def render_metrics() -> Tuple[bytes, str]:
    """Return the Prometheus text exposition payload."""

    return (
        generate_latest(
            METRICS_REGISTRY
        ),
        CONTENT_TYPE_LATEST,
    )
