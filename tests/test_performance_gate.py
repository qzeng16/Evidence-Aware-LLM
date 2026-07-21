"""Tests for stable performance smoke thresholds."""

from app.performance_gate import (
    evaluate_performance_gate,
)


def valid_summary():
    """Return one passing performance summary."""

    return {
        "completed_requests": 20,
        "successful_requests": 20,
        "failed_requests": 0,
        "success_rate": 1.0,
        "throughput_rps": 5.0,
        "latency_ms": {
            "p95": 900.0,
        },
        "status_code_counts": {
            "200": 20,
        },
    }


def evaluate(summary):
    """Evaluate using the CI smoke thresholds."""

    return evaluate_performance_gate(
        summary,
        expected_requests=20,
        min_success_rate=1.0,
        min_throughput_rps=1.0,
        max_p95_latency_ms=5000.0,
    )


def test_valid_summary_passes_gate():
    assert evaluate(valid_summary()) == []


def test_completed_request_mismatch_fails_gate():
    summary = valid_summary()
    summary["completed_requests"] = 19

    errors = evaluate(summary)

    assert any(
        "Completed 19 requests"
        in error
        for error in errors
    )


def test_request_failure_fails_gate():
    summary = valid_summary()
    summary["successful_requests"] = 19
    summary["failed_requests"] = 1
    summary["success_rate"] = 0.95

    errors = evaluate(summary)

    assert any(
        "zero failures"
        in error
        for error in errors
    )

    assert any(
        "Success rate"
        in error
        for error in errors
    )


def test_low_throughput_fails_gate():
    summary = valid_summary()
    summary["throughput_rps"] = 0.5

    errors = evaluate(summary)

    assert any(
        "Throughput"
        in error
        for error in errors
    )


def test_high_p95_latency_fails_gate():
    summary = valid_summary()
    summary["latency_ms"]["p95"] = 6000.0

    errors = evaluate(summary)

    assert any(
        "P95 latency"
        in error
        for error in errors
    )


def test_unexpected_status_counts_fail_gate():
    summary = valid_summary()
    summary["status_code_counts"] = {
        "200": 19,
        "503": 1,
    }

    errors = evaluate(summary)

    assert any(
        "HTTP status counts"
        in error
        for error in errors
    )
