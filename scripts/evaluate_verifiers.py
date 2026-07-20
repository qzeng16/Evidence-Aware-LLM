#!/usr/bin/env python3
"""Compare rule-only, LLM-only, and hybrid verification modes."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from sentence_transformers import SentenceTransformer

import layer0_verifier as core_verifier
from app.config import (
    DEFAULT_OPENAI_MAX_RETRIES,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
)
from app.evaluation import (
    BenchmarkCase,
    EvaluationOutcome,
    load_benchmark,
    render_markdown_report,
    summarize_outcomes,
)
from app.llm_clients import (
    LLMClient,
    LLMClientResponse,
    OpenAIResponsesClient,
)
from app.verifiers import (
    HybridVerifier,
    LLMVerifier,
    RuleVerifier,
    Verifier,
)


SUPPORTED_MODES = (
    "rule_only",
    "llm_only",
    "hybrid",
)


class RecordingLLMClient:
    """Record token and request usage around another LLM client."""

    def __init__(
        self,
        inner_client: LLMClient,
    ) -> None:
        self._inner_client = inner_client
        self.call_count = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def generate(
        self,
        messages: Sequence[
            Mapping[str, str]
        ],
        response_schema: Mapping[str, Any],
    ) -> LLMClientResponse:
        """Generate a response and record usage."""

        response = self._inner_client.generate(
            messages=messages,
            response_schema=response_schema,
        )

        self.call_count += 1
        self.input_tokens += (
            response.input_tokens or 0
        )
        self.output_tokens += (
            response.output_tokens or 0
        )

        return response


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate rule_only, llm_only, and "
            "hybrid verifier modes."
        )
    )

    parser.add_argument(
        "--benchmark",
        default="evaluation/benchmark.jsonl",
        help="Path to the JSONL benchmark.",
    )

    parser.add_argument(
        "--output-dir",
        default="evaluation/results",
        help="Directory for latest.json and latest.md.",
    )

    parser.add_argument(
        "--modes",
        nargs="+",
        choices=SUPPORTED_MODES,
        default=list(SUPPORTED_MODES),
        help="Verifier modes to evaluate.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optionally evaluate only the first N cases.",
    )

    return parser.parse_args()


def require_openai_key(
    modes: Sequence[str],
) -> Optional[str]:
    """Read the OpenAI key only when an LLM mode is requested."""

    uses_llm = any(
        mode in {
            "llm_only",
            "hybrid",
        }
        for mode in modes
    )

    if not uses_llm:
        return None

    api_key = os.environ.get(
        "OPENAI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is required when "
            "evaluating llm_only or hybrid."
        )

    return api_key


def build_verifier(
    mode: str,
    evidence_db: List[Dict[str, Any]],
    verification_rules: List[
        Dict[str, Any]
    ],
    model: Any,
    evidence_embeddings: Any,
    api_key: Optional[str],
    openai_model: str,
) -> Dict[str, Any]:
    """Build one verifier and optional usage recorder."""

    rule_verifier = RuleVerifier(
        evidence_db=evidence_db,
        verification_rules=verification_rules,
        model=model,
        evidence_embeddings=evidence_embeddings,
    )

    if mode == "rule_only":
        return {
            "verifier": rule_verifier,
            "recorder": None,
        }

    provider_client = OpenAIResponsesClient(
        api_key=api_key or "",
        model=openai_model,
        timeout_seconds=float(
            os.environ.get(
                "OPENAI_TIMEOUT_SECONDS",
                str(
                    DEFAULT_OPENAI_TIMEOUT_SECONDS
                ),
            )
        ),
        max_retries=int(
            os.environ.get(
                "OPENAI_MAX_RETRIES",
                str(
                    DEFAULT_OPENAI_MAX_RETRIES
                ),
            )
        ),
    )

    recorder = RecordingLLMClient(
        provider_client
    )

    llm_verifier = LLMVerifier(
        evidence_db=evidence_db,
        model=model,
        evidence_embeddings=evidence_embeddings,
        client=recorder,
    )

    if mode == "llm_only":
        active_verifier: Verifier = (
            llm_verifier
        )
    elif mode == "hybrid":
        active_verifier = HybridVerifier(
            rule_verifier=rule_verifier,
            llm_verifier=llm_verifier,
        )
    else:
        raise ValueError(
            f"Unsupported mode: {mode}"
        )

    return {
        "verifier": active_verifier,
        "recorder": recorder,
    }


def evaluate_case(
    case: BenchmarkCase,
    verifier: Verifier,
    recorder: Optional[
        RecordingLLMClient
    ],
) -> EvaluationOutcome:
    """Evaluate one case and capture runtime usage."""

    calls_before = (
        recorder.call_count
        if recorder is not None
        else 0
    )

    input_before = (
        recorder.input_tokens
        if recorder is not None
        else 0
    )

    output_before = (
        recorder.output_tokens
        if recorder is not None
        else 0
    )

    started_at = perf_counter()

    try:
        run = verifier.verify(
            case.claim
        )

        latency_ms = (
            perf_counter() - started_at
        ) * 1000.0

        predicted_label = (
            run.result.label.value
        )

        confidence = (
            run.result.confidence
        )

        verifier_type = (
            run.result.verifier_type.value
        )

        matched_evidence_ids = (
            run.result.matched_evidence_ids
        )

        abstention_reason = (
            run.result.abstention_reason
        )

        error_code = None
        error_type = None

    except Exception as error:
        latency_ms = (
            perf_counter() - started_at
        ) * 1000.0

        predicted_label = None
        confidence = None
        verifier_type = None
        matched_evidence_ids = ()
        abstention_reason = None

        error_code = getattr(
            error,
            "error_code",
            None,
        )

        error_type = type(error).__name__

    calls_after = (
        recorder.call_count
        if recorder is not None
        else 0
    )

    input_after = (
        recorder.input_tokens
        if recorder is not None
        else 0
    )

    output_after = (
        recorder.output_tokens
        if recorder is not None
        else 0
    )

    return EvaluationOutcome(
        case_id=case.case_id,
        claim=case.claim,
        category=case.category,
        expected_label=case.expected_label,
        predicted_label=predicted_label,
        confidence=confidence,
        verifier_type=verifier_type,
        correct=(
            predicted_label
            == case.expected_label
        ),
        latency_ms=latency_ms,
        matched_evidence_ids=(
            matched_evidence_ids
        ),
        abstention_reason=(
            abstention_reason
        ),
        llm_calls=(
            calls_after - calls_before
        ),
        input_tokens=(
            input_after - input_before
        ),
        output_tokens=(
            output_after - output_before
        ),
        error_code=(
            str(error_code)
            if error_code is not None
            else None
        ),
        error_type=error_type,
    )


def main() -> int:
    """Run the complete evaluation."""

    arguments = parse_arguments()

    benchmark_path = Path(
        arguments.benchmark
    )

    output_dir = Path(
        arguments.output_dir
    )

    cases = load_benchmark(
        benchmark_path
    )

    if arguments.limit is not None:
        if arguments.limit <= 0:
            raise SystemExit(
                "--limit must be greater than zero."
            )

        cases = cases[
            :arguments.limit
        ]

    api_key = require_openai_key(
        arguments.modes
    )

    openai_model = os.environ.get(
        "OPENAI_MODEL",
        DEFAULT_OPENAI_MODEL,
    ).strip()

    print(
        f"Loading {len(cases)} benchmark cases..."
    )

    evidence_db = core_verifier.load_evidence(
        core_verifier.DATA_PATH
    )

    verification_rules = (
        core_verifier.load_rules(
            core_verifier.RULES_PATH
        )
    )

    print(
        "Loading embedding model: "
        f"{core_verifier.MODEL_NAME}"
    )

    embedding_model = (
        SentenceTransformer(
            core_verifier.MODEL_NAME
        )
    )

    evidence_embeddings = (
        core_verifier
        .get_or_build_evidence_embeddings(
            evidence_db,
            embedding_model,
        )
    )

    outcomes_by_mode: Dict[
        str,
        List[EvaluationOutcome],
    ] = {}

    summaries = []

    for mode in arguments.modes:
        print()
        print(
            f"Evaluating mode: {mode}"
        )

        components = build_verifier(
            mode=mode,
            evidence_db=evidence_db,
            verification_rules=(
                verification_rules
            ),
            model=embedding_model,
            evidence_embeddings=(
                evidence_embeddings
            ),
            api_key=api_key,
            openai_model=openai_model,
        )

        active_verifier = components[
            "verifier"
        ]

        recorder = components[
            "recorder"
        ]

        mode_outcomes = []

        for index, case in enumerate(
            cases,
            start=1,
        ):
            outcome = evaluate_case(
                case=case,
                verifier=active_verifier,
                recorder=recorder,
            )

            mode_outcomes.append(
                outcome
            )

            print(
                f"[{index}/{len(cases)}] "
                f"{case.case_id}: "
                f"{outcome.predicted_label or 'Error'} "
                f"(expected "
                f"{case.expected_label})"
            )

        outcomes_by_mode[
            mode
        ] = mode_outcomes

        summaries.append(
            summarize_outcomes(
                mode,
                mode_outcomes,
            )
        )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    report_data = {
        "metadata": {
            "benchmark": str(
                benchmark_path
            ),
            "generated_at": generated_at,
            "openai_model": openai_model,
            "modes": list(
                arguments.modes
            ),
            "case_count": len(cases),
        },
        "summaries": summaries,
        "outcomes": {
            mode: [
                outcome.to_dict()
                for outcome in outcomes
            ]
            for mode, outcomes in (
                outcomes_by_mode.items()
            )
        },
    }

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir / "latest.json"
    )

    markdown_path = (
        output_dir / "latest.md"
    )

    json_path.write_text(
        json.dumps(
            report_data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown_path.write_text(
        render_markdown_report(
            benchmark_name=str(
                benchmark_path
            ),
            generated_at=generated_at,
            model=openai_model,
            summaries=summaries,
            outcomes_by_mode=(
                outcomes_by_mode
            ),
        ),
        encoding="utf-8",
    )

    print()
    print("Evaluation complete.")

    for summary in summaries:
        print(
            "{mode}: accuracy={accuracy:.1%}, "
            "abstention={abstention_rate:.1%}, "
            "avg_latency={average_latency_ms:.1f}ms, "
            "llm_calls={llm_call_count}, "
            "tokens={total_tokens}".format(
                **summary
            )
        )

    print(
        f"JSON report: {json_path}"
    )

    print(
        f"Markdown report: {markdown_path}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
