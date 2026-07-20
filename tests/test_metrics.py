"""Tests for Prometheus application metrics."""

import asyncio
from typing import Any, Dict, List

from prometheus_client import (
    CONTENT_TYPE_LATEST,
)
from prometheus_client.parser import (
    text_string_to_metric_families,
)

from app.metrics import (
    normalize_metric_path,
    record_http_request,
    record_verification_response,
    render_metrics,
)
from app.observability import (
    RequestLoggingMiddleware,
)
from app.routes import metrics_endpoint


def metrics_text() -> str:
    """Return the current metrics registry as text."""

    payload, _ = render_metrics()

    return payload.decode("utf-8")


def metric_sample_value(
    text: str,
    name: str,
    **expected_labels: str,
) -> float:
    """Read one metric sample without relying on label order."""

    for family in text_string_to_metric_families(
        text
    ):
        for sample in family.samples:
            if (
                sample.name == name
                and sample.labels
                == expected_labels
            ):
                return float(sample.value)

    return 0.0


def test_metric_path_is_low_cardinality() -> None:
    """Known paths remain visible and unknown paths are grouped."""

    assert normalize_metric_path(
        "/health"
    ) == "/health"

    assert normalize_metric_path(
        "/users/private-value"
    ) == "/other"


def test_http_request_metrics_are_recorded() -> None:
    """HTTP totals and latency should use safe labels."""

    record_http_request(
        method="PATCH",
        path="/health",
        status_code=204,
        latency_ms=25.0,
    )

    output = metrics_text()

    assert (
        'evidence_http_requests_total'
        '{method="PATCH",path="/health",'
        'status_code="204"} 1.0'
        in output
    )

    assert (
        'evidence_http_request_duration_seconds_count'
        '{method="PATCH",path="/health"} 1.0'
        in output
    )

    assert (
        'evidence_http_request_duration_seconds_sum'
        '{method="PATCH",path="/health"} 0.025'
        in output
    )


def test_successful_verification_metrics_are_recorded() -> None:
    """Successful results should update outcome and label metrics."""

    record_verification_response(
        {
            "status": "success",
            "data": {
                "verification": {
                    "label": "Refuted",
                    "confidence": 0.73,
                    "verifier_type": "hybrid",
                }
            },
        }
    )

    output = metrics_text()

    assert (
        'evidence_verification_requests_total'
        '{outcome="success"}'
        in output
    )

    assert (
        'evidence_verification_results_total'
        '{label="Refuted",verifier_type="hybrid"}'
        in output
    )

    assert (
        'evidence_verification_confidence_count'
        '{label="Refuted",verifier_type="hybrid"}'
        in output
    )


def test_failed_verification_records_only_outcome() -> None:
    """Error responses should not invent labels or confidence."""

    record_verification_response(
        {
            "status": "error",
            "error": {
                "type": "service_unavailable",
            },
        }
    )

    output = metrics_text()

    assert (
        'evidence_verification_requests_total'
        '{outcome="error"}'
        in output
    )


def test_metrics_endpoint_uses_prometheus_content_type() -> None:
    """The route should return Prometheus text without secrets."""

    response = metrics_endpoint()

    content_type = response.headers.get(
        "content-type",
        "",
    )

    assert (
        content_type.lower()
        == CONTENT_TYPE_LATEST.lower()
    )

    body = response.body.decode("utf-8")

    assert "evidence_http_requests_total" in body
    assert "OPENAI_API_KEY" not in body
    assert "sk-proj-" not in body
    assert "hf_private_token" not in body
    assert "private-claim-value" not in body


def test_middleware_records_http_metrics() -> None:
    """The request middleware should update Prometheus counters."""

    async def app(
        scope: Dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 207,
                "headers": [],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )

    scope: Dict[str, Any] = {
        "type": "http",
        "asgi": {
            "version": "3.0",
        },
        "http_version": "1.1",
        "method": "OPTIONS",
        "scheme": "http",
        "path": "/private-dynamic-path",
        "raw_path": b"/private-dynamic-path",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": (
            "127.0.0.1",
            50000,
        ),
        "server": (
            "testserver",
            80,
        ),
    }

    messages: List[
        Dict[str, Any]
    ] = []

    async def receive() -> Dict[str, Any]:
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

    async def send(
        message: Dict[str, Any],
    ) -> None:
        messages.append(message)

    before = metric_sample_value(
        metrics_text(),
        "evidence_http_requests_total",
        method="OPTIONS",
        path="/other",
        status_code="207",
    )

    asyncio.run(
        RequestLoggingMiddleware(app)(
            scope,
            receive,
            send,
        )
    )

    after = metric_sample_value(
        metrics_text(),
        "evidence_http_requests_total",
        method="OPTIONS",
        path="/other",
        status_code="207",
    )

    assert after - before == 1.0
