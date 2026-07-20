"""Reusable API load-test statistics."""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RequestSample:
    """One completed HTTP request attempt."""

    latency_ms: float
    status_code: Optional[int]
    success: bool
    error_type: Optional[str] = None


def percentile(
    values: List[float],
    percentile_value: float,
) -> float:
    """Calculate a nearest-rank percentile."""

    if not 0.0 <= percentile_value <= 1.0:
        raise ValueError(
            "percentile_value must be between 0 and 1."
        )

    if not values:
        return 0.0

    ordered = sorted(
        max(float(value), 0.0)
        for value in values
    )

    rank = max(
        1,
        math.ceil(
            percentile_value
            * len(ordered)
        ),
    )

    return ordered[
        min(rank, len(ordered)) - 1
    ]


def summarize_samples(
    samples: List[RequestSample],
    *,
    elapsed_seconds: float,
    endpoint: str,
    concurrency: int,
) -> Dict[str, Any]:
    """Build a JSON-serializable load-test summary."""

    completed_requests = len(samples)

    successful_requests = sum(
        1
        for sample in samples
        if sample.success
    )

    failed_requests = (
        completed_requests
        - successful_requests
    )

    safe_elapsed_seconds = max(
        float(elapsed_seconds),
        0.0,
    )

    latencies = [
        max(float(sample.latency_ms), 0.0)
        for sample in samples
    ]

    status_code_counts: Dict[str, int] = {}
    error_type_counts: Dict[str, int] = {}

    for sample in samples:
        status_key = (
            str(sample.status_code)
            if sample.status_code is not None
            else "none"
        )

        status_code_counts[status_key] = (
            status_code_counts.get(
                status_key,
                0,
            )
            + 1
        )

        if sample.error_type:
            error_type_counts[
                sample.error_type
            ] = (
                error_type_counts.get(
                    sample.error_type,
                    0,
                )
                + 1
            )

    if completed_requests:
        success_rate = (
            successful_requests
            / completed_requests
        )

        average_latency_ms = (
            sum(latencies)
            / completed_requests
        )
    else:
        success_rate = 0.0
        average_latency_ms = 0.0

    throughput_rps = (
        completed_requests
        / safe_elapsed_seconds
        if safe_elapsed_seconds > 0
        else 0.0
    )

    return {
        "endpoint": endpoint,
        "concurrency": concurrency,
        "elapsed_seconds": round(
            safe_elapsed_seconds,
            3,
        ),
        "completed_requests": (
            completed_requests
        ),
        "successful_requests": (
            successful_requests
        ),
        "failed_requests": failed_requests,
        "success_rate": round(
            success_rate,
            4,
        ),
        "error_rate": round(
            1.0 - success_rate
            if completed_requests
            else 0.0,
            4,
        ),
        "throughput_rps": round(
            throughput_rps,
            3,
        ),
        "latency_ms": {
            "minimum": round(
                min(latencies)
                if latencies
                else 0.0,
                3,
            ),
            "average": round(
                average_latency_ms,
                3,
            ),
            "p50": round(
                percentile(
                    latencies,
                    0.50,
                ),
                3,
            ),
            "p95": round(
                percentile(
                    latencies,
                    0.95,
                ),
                3,
            ),
            "p99": round(
                percentile(
                    latencies,
                    0.99,
                ),
                3,
            ),
            "maximum": round(
                max(latencies)
                if latencies
                else 0.0,
                3,
            ),
        },
        "status_code_counts": (
            status_code_counts
        ),
        "error_type_counts": (
            error_type_counts
        ),
    }
