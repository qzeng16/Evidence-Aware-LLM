"""Evaluation utilities for verifier comparison experiments."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Sequence


VALID_LABELS = {
    "Supported",
    "Refuted",
    "Uncertain",
}


@dataclass(frozen=True)
class BenchmarkCase:
    """One manually labeled evaluation case."""

    case_id: str
    claim: str
    expected_label: str
    category: str

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "BenchmarkCase":
        """Validate and construct one benchmark case."""

        case_id = str(
            value.get("id", "")
        ).strip()

        claim = str(
            value.get("claim", "")
        ).strip()

        expected_label = str(
            value.get(
                "expected_label",
                "",
            )
        ).strip()

        category = str(
            value.get(
                "category",
                "uncategorized",
            )
        ).strip()

        if not case_id:
            raise ValueError(
                "Benchmark case id cannot be empty."
            )

        if not claim:
            raise ValueError(
                f"Claim cannot be empty for {case_id}."
            )

        if expected_label not in VALID_LABELS:
            raise ValueError(
                f"Unsupported expected label "
                f"'{expected_label}' for {case_id}."
            )

        if not category:
            category = "uncategorized"

        return cls(
            case_id=case_id,
            claim=claim,
            expected_label=expected_label,
            category=category,
        )


@dataclass(frozen=True)
class EvaluationOutcome:
    """One verifier prediction and its runtime metadata."""

    case_id: str
    claim: str
    category: str
    expected_label: str
    predicted_label: Optional[str]
    confidence: Optional[float]
    verifier_type: Optional[str]
    correct: bool
    latency_ms: float
    matched_evidence_ids: Sequence[str]
    abstention_reason: Optional[str]
    llm_calls: int
    input_tokens: int
    output_tokens: int
    error_code: Optional[str] = None
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize an evaluation outcome."""

        return {
            "case_id": self.case_id,
            "claim": self.claim,
            "category": self.category,
            "expected_label": self.expected_label,
            "predicted_label": self.predicted_label,
            "confidence": self.confidence,
            "verifier_type": self.verifier_type,
            "correct": self.correct,
            "latency_ms": round(
                self.latency_ms,
                3,
            ),
            "matched_evidence_ids": list(
                self.matched_evidence_ids
            ),
            "abstention_reason": (
                self.abstention_reason
            ),
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": (
                self.input_tokens
                + self.output_tokens
            ),
            "error_code": self.error_code,
            "error_type": self.error_type,
        }


def load_benchmark(
    path: Path,
) -> List[BenchmarkCase]:
    """Load and validate a JSONL benchmark."""

    cases: List[BenchmarkCase] = []
    seen_ids = set()

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, raw_line in enumerate(
            file,
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on line "
                    f"{line_number}."
                ) from error

            if not isinstance(value, dict):
                raise ValueError(
                    f"Benchmark line {line_number} "
                    "must contain an object."
                )

            case = BenchmarkCase.from_dict(
                value
            )

            if case.case_id in seen_ids:
                raise ValueError(
                    f"Duplicate benchmark id: "
                    f"{case.case_id}"
                )

            seen_ids.add(case.case_id)
            cases.append(case)

    if not cases:
        raise ValueError(
            "Benchmark contains no cases."
        )

    return cases


def percentile(
    values: Sequence[float],
    percentile_value: float,
) -> float:
    """Calculate a nearest-rank percentile."""

    if not values:
        return 0.0

    ordered_values = sorted(
        float(value)
        for value in values
    )

    rank = max(
        1,
        math.ceil(
            percentile_value
            * len(ordered_values)
        ),
    )

    return ordered_values[
        rank - 1
    ]


def summarize_outcomes(
    mode: str,
    outcomes: Sequence[EvaluationOutcome],
) -> Dict[str, Any]:
    """Calculate mode-level evaluation metrics."""

    total_cases = len(outcomes)

    if total_cases == 0:
        raise ValueError(
            "At least one outcome is required."
        )

    completed = [
        outcome
        for outcome in outcomes
        if outcome.predicted_label is not None
    ]

    correct_count = sum(
        1
        for outcome in outcomes
        if outcome.correct
    )

    uncertain_count = sum(
        1
        for outcome in completed
        if outcome.predicted_label
        == "Uncertain"
    )

    decisive_count = len(
        completed
    ) - uncertain_count

    latencies = [
        outcome.latency_ms
        for outcome in outcomes
    ]

    confidence_values = [
        outcome.confidence
        for outcome in completed
        if outcome.confidence is not None
    ]

    total_llm_calls = sum(
        outcome.llm_calls
        for outcome in outcomes
    )

    input_tokens = sum(
        outcome.input_tokens
        for outcome in outcomes
    )

    output_tokens = sum(
        outcome.output_tokens
        for outcome in outcomes
    )

    completed_count = len(completed)
    error_count = (
        total_cases - completed_count
    )

    return {
        "mode": mode,
        "total_cases": total_cases,
        "completed_cases": completed_count,
        "error_count": error_count,
        "correct_cases": correct_count,
        "accuracy": round(
            correct_count / total_cases,
            4,
        ),
        "coverage": round(
            decisive_count / total_cases,
            4,
        ),
        "abstention_rate": round(
            uncertain_count / total_cases,
            4,
        ),
        "average_confidence": round(
            mean(confidence_values)
            if confidence_values
            else 0.0,
            4,
        ),
        "average_latency_ms": round(
            mean(latencies),
            3,
        ),
        "p95_latency_ms": round(
            percentile(
                latencies,
                0.95,
            ),
            3,
        ),
        "llm_call_count": total_llm_calls,
        "llm_call_rate": round(
            total_llm_calls / total_cases,
            4,
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": (
            input_tokens
            + output_tokens
        ),
    }


def render_markdown_report(
    benchmark_name: str,
    generated_at: str,
    model: str,
    summaries: Sequence[
        Mapping[str, Any]
    ],
    outcomes_by_mode: Mapping[
        str,
        Sequence[EvaluationOutcome],
    ],
) -> str:
    """Render a human-readable evaluation report."""

    lines = [
        "# Verifier Evaluation Report",
        "",
        f"- Benchmark: `{benchmark_name}`",
        f"- Generated at: `{generated_at}`",
        f"- Configured LLM model: `{model}`",
        "",
        "## Summary",
        "",
        (
            "| Mode | Accuracy | Coverage | "
            "Abstention | Avg latency | P95 latency | "
            "LLM calls | Tokens | Errors |"
        ),
        (
            "|---|---:|---:|---:|---:|---:|"
            "---:|---:|---:|"
        ),
    ]

    for summary in summaries:
        lines.append(
            "| {mode} | {accuracy:.1%} | "
            "{coverage:.1%} | "
            "{abstention_rate:.1%} | "
            "{average_latency_ms:.1f} ms | "
            "{p95_latency_ms:.1f} ms | "
            "{llm_call_count} | "
            "{total_tokens} | "
            "{error_count} |".format(
                **summary
            )
        )

    for mode, outcomes in (
        outcomes_by_mode.items()
    ):
        lines.extend(
            [
                "",
                f"## Results: `{mode}`",
                "",
                (
                    "| ID | Expected | Predicted | "
                    "Correct | Confidence | "
                    "Latency | LLM calls |"
                ),
                (
                    "|---|---|---|---:|---:|"
                    "---:|---:|"
                ),
            ]
        )

        for outcome in outcomes:
            confidence = (
                f"{outcome.confidence:.2f}"
                if outcome.confidence
                is not None
                else "—"
            )

            predicted_label = (
                outcome.predicted_label
                or "Error"
            )

            lines.append(
                f"| {outcome.case_id} | "
                f"{outcome.expected_label} | "
                f"{predicted_label} | "
                f"{'Yes' if outcome.correct else 'No'} | "
                f"{confidence} | "
                f"{outcome.latency_ms:.1f} ms | "
                f"{outcome.llm_calls} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "This is a small, manually curated "
                "regression benchmark for comparing "
                "the three project modes. It is not "
                "evidence of general-purpose "
                "fact-checking accuracy."
            ),
            "",
        ]
    )

    return "\n".join(lines)
