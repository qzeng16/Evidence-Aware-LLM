"""Tests for verifier evaluation metrics and reporting."""

import json
from pathlib import Path

import pytest

from app.evaluation import (
    EvaluationOutcome,
    load_benchmark,
    percentile,
    render_markdown_report,
    summarize_outcomes,
)


def build_outcome(
    case_id: str,
    expected: str,
    predicted: str,
    latency_ms: float,
    llm_calls: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> EvaluationOutcome:
    """Build one deterministic outcome."""

    return EvaluationOutcome(
        case_id=case_id,
        claim=f"Claim {case_id}",
        category="test",
        expected_label=expected,
        predicted_label=predicted,
        confidence=0.8,
        verifier_type="hybrid",
        correct=expected == predicted,
        latency_ms=latency_ms,
        matched_evidence_ids=(),
        abstention_reason=(
            "test_abstention"
            if predicted == "Uncertain"
            else None
        ),
        llm_calls=llm_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def test_load_benchmark(
    tmp_path: Path,
):
    """Valid JSONL cases should load successfully."""

    path = tmp_path / "benchmark.jsonl"

    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "case-001",
                        "claim": "Supported claim.",
                        "expected_label": "Supported",
                        "category": "test",
                    }
                ),
                json.dumps(
                    {
                        "id": "case-002",
                        "claim": "Uncertain claim.",
                        "expected_label": "Uncertain",
                        "category": "test",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_benchmark(path)

    assert len(cases) == 2
    assert cases[0].case_id == "case-001"
    assert (
        cases[1].expected_label
        == "Uncertain"
    )


def test_duplicate_benchmark_id_is_rejected(
    tmp_path: Path,
):
    """Benchmark IDs must be unique."""

    path = tmp_path / "benchmark.jsonl"

    item = {
        "id": "duplicate",
        "claim": "A claim.",
        "expected_label": "Supported",
        "category": "test",
    }

    path.write_text(
        json.dumps(item)
        + "\n"
        + json.dumps(item)
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate benchmark id",
    ):
        load_benchmark(path)


def test_percentile_uses_nearest_rank():
    """P95 should use the nearest-rank result."""

    assert percentile(
        [10.0, 20.0, 30.0, 40.0],
        0.95,
    ) == 40.0

    assert percentile([], 0.95) == 0.0


def test_summary_metrics():
    """Metrics should include accuracy, usage, and abstention."""

    outcomes = [
        build_outcome(
            "case-001",
            "Supported",
            "Supported",
            100.0,
            llm_calls=1,
            input_tokens=100,
            output_tokens=20,
        ),
        build_outcome(
            "case-002",
            "Refuted",
            "Supported",
            200.0,
            llm_calls=1,
            input_tokens=110,
            output_tokens=25,
        ),
        build_outcome(
            "case-003",
            "Uncertain",
            "Uncertain",
            300.0,
            llm_calls=0,
        ),
    ]

    summary = summarize_outcomes(
        "hybrid",
        outcomes,
    )

    assert summary["total_cases"] == 3
    assert summary["correct_cases"] == 2
    assert summary["accuracy"] == 0.6667
    assert summary["coverage"] == 0.6667
    assert (
        summary["abstention_rate"]
        == 0.3333
    )
    assert summary["average_latency_ms"] == (
        200.0
    )
    assert summary["p95_latency_ms"] == (
        300.0
    )
    assert summary["llm_call_count"] == 2
    assert summary["input_tokens"] == 210
    assert summary["output_tokens"] == 45
    assert summary["total_tokens"] == 255


def test_markdown_report_contains_modes():
    """The report should expose comparison metrics."""

    outcomes = [
        build_outcome(
            "case-001",
            "Supported",
            "Supported",
            100.0,
        )
    ]

    summary = summarize_outcomes(
        "rule_only",
        outcomes,
    )

    report = render_markdown_report(
        benchmark_name="benchmark.jsonl",
        generated_at="2026-07-20T00:00:00Z",
        model="test-model",
        summaries=[summary],
        outcomes_by_mode={
            "rule_only": outcomes,
        },
    )

    assert "# Verifier Evaluation Report" in report
    assert "| rule_only |" in report
    assert "case-001" in report
    assert "not evidence of general-purpose" in report
