"""Stable performance smoke-gate validation."""

from typing import Any, Dict, List


def evaluate_performance_gate(
    summary: Dict[str, Any],
    *,
    expected_requests: int,
    min_success_rate: float,
    min_throughput_rps: float,
    max_p95_latency_ms: float,
) -> List[str]:
    """Return human-readable performance-gate failures."""

    completed_requests = int(
        summary["completed_requests"]
    )

    successful_requests = int(
        summary["successful_requests"]
    )

    failed_requests = int(
        summary["failed_requests"]
    )

    success_rate = float(
        summary["success_rate"]
    )

    throughput_rps = float(
        summary["throughput_rps"]
    )

    p95_latency_ms = float(
        summary["latency_ms"]["p95"]
    )

    status_code_counts = summary[
        "status_code_counts"
    ]

    errors = []

    if completed_requests != expected_requests:
        errors.append(
            "Completed {} requests instead of {}.".format(
                completed_requests,
                expected_requests,
            )
        )

    if (
        successful_requests
        != expected_requests
        or failed_requests != 0
    ):
        errors.append(
            "Expected {} successful requests and "
            "zero failures; observed {} successful "
            "and {} failed.".format(
                expected_requests,
                successful_requests,
                failed_requests,
            )
        )

    if success_rate < min_success_rate:
        errors.append(
            "Success rate {:.2%} was below "
            "{:.2%}.".format(
                success_rate,
                min_success_rate,
            )
        )

    if throughput_rps < min_throughput_rps:
        errors.append(
            "Throughput {:.3f} requests/second "
            "was below {:.3f}.".format(
                throughput_rps,
                min_throughput_rps,
            )
        )

    if p95_latency_ms > max_p95_latency_ms:
        errors.append(
            "P95 latency {:.3f} ms exceeded "
            "{:.3f} ms.".format(
                p95_latency_ms,
                max_p95_latency_ms,
            )
        )

    expected_status_counts = {
        "200": expected_requests,
    }

    if status_code_counts != expected_status_counts:
        errors.append(
            "Unexpected HTTP status counts: {}.".format(
                status_code_counts
            )
        )

    return errors
