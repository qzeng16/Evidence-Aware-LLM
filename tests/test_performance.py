"""Tests for API performance summaries."""

import pytest

from app.performance import (
    RequestSample,
    percentile,
    summarize_samples,
)


def sample(
    latency_ms,
    *,
    status_code=200,
    success=True,
    error_type=None,
):
    """Create one concise request sample."""

    return RequestSample(
        latency_ms=latency_ms,
        status_code=status_code,
        success=success,
        error_type=error_type,
    )


def test_percentile_returns_zero_for_empty_values():
    assert percentile([], 0.95) == 0.0


def test_percentile_uses_nearest_rank():
    values = [
        10.0,
        20.0,
        30.0,
        40.0,
    ]

    assert percentile(values, 0.50) == 20.0
    assert percentile(values, 0.95) == 40.0
    assert percentile(values, 0.99) == 40.0


def test_percentile_rejects_invalid_probability():
    with pytest.raises(
        ValueError,
        match="between 0 and 1",
    ):
        percentile(
            [10.0],
            1.1,
        )


def test_summary_counts_successes_and_failures():
    summary = summarize_samples(
        [
            sample(10.0),
            sample(20.0),
            sample(
                30.0,
                status_code=503,
                success=False,
                error_type="http_error",
            ),
        ],
        elapsed_seconds=1.0,
        endpoint="/verify",
        concurrency=2,
    )

    assert summary[
        "completed_requests"
    ] == 3

    assert summary[
        "successful_requests"
    ] == 2

    assert summary[
        "failed_requests"
    ] == 1

    assert summary[
        "success_rate"
    ] == 0.6667

    assert summary[
        "error_rate"
    ] == 0.3333


def test_summary_records_status_and_error_counts():
    summary = summarize_samples(
        [
            sample(10.0),
            sample(
                20.0,
                status_code=503,
                success=False,
                error_type="http_error",
            ),
            sample(
                30.0,
                status_code=None,
                success=False,
                error_type="timeout",
            ),
        ],
        elapsed_seconds=1.0,
        endpoint="/ready",
        concurrency=3,
    )

    assert summary[
        "status_code_counts"
    ] == {
        "200": 1,
        "503": 1,
        "none": 1,
    }

    assert summary[
        "error_type_counts"
    ] == {
        "http_error": 1,
        "timeout": 1,
    }


def test_summary_calculates_latency_and_throughput():
    summary = summarize_samples(
        [
            sample(10.0),
            sample(20.0),
            sample(30.0),
            sample(40.0),
        ],
        elapsed_seconds=2.0,
        endpoint="/live",
        concurrency=4,
    )

    assert summary[
        "throughput_rps"
    ] == 2.0

    assert summary[
        "latency_ms"
    ] == {
        "minimum": 10.0,
        "average": 25.0,
        "p50": 20.0,
        "p95": 40.0,
        "p99": 40.0,
        "maximum": 40.0,
    }


def test_summary_handles_no_completed_requests():
    summary = summarize_samples(
        [],
        elapsed_seconds=0.0,
        endpoint="/health",
        concurrency=1,
    )

    assert summary[
        "completed_requests"
    ] == 0

    assert summary[
        "success_rate"
    ] == 0.0

    assert summary[
        "throughput_rps"
    ] == 0.0

    assert summary[
        "latency_ms"
    ]["p95"] == 0.0
