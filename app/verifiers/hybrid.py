"""Cost-aware and fault-tolerant hybrid claim verifier."""

from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Sequence,
    Tuple,
)

from app.llm_clients import LLMClientError
from app.llm_judge_parser import (
    LLMJudgeResponseParseError,
)
from app.llm_judge_prompt import (
    LLMJudgePromptError,
)
from app.verification_result import (
    VerificationLabel,
    VerificationResult,
    VerifierType,
)
from app.verifiers.base import (
    VerificationRun,
    Verifier,
)


DECISIVE_LABELS = {
    VerificationLabel.SUPPORTED,
    VerificationLabel.REFUTED,
}

EXPECTED_LLM_ERRORS = (
    LLMClientError,
    LLMJudgeResponseParseError,
    LLMJudgePromptError,
)


def _normalize_probability(
    value: float,
    field_name: str,
) -> float:
    """Validate a probability-like configuration value."""

    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be a number."
        )

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a number."
        ) from error

    if not 0.0 <= normalized_value <= 1.0:
        raise ValueError(
            f"{field_name} must be between 0 and 1."
        )

    return normalized_value


def _clamp_confidence(
    value: float,
) -> float:
    """Clamp and round a confidence value."""

    return round(
        max(
            0.0,
            min(1.0, float(value)),
        ),
        4,
    )


def _is_decisive(
    result: VerificationResult,
) -> bool:
    """Return whether a result makes a decisive claim."""

    return result.label in DECISIVE_LABELS


def _merge_evidence_ids(
    *id_groups: Iterable[str],
) -> Tuple[str, ...]:
    """Merge evidence IDs while preserving order."""

    merged_ids: List[str] = []
    seen_ids = set()

    for id_group in id_groups:
        for raw_id in id_group:
            evidence_id = str(raw_id).strip()

            if (
                not evidence_id
                or evidence_id in seen_ids
            ):
                continue

            seen_ids.add(evidence_id)
            merged_ids.append(evidence_id)

    return tuple(merged_ids)


def _evidence_key(
    evidence: Dict[str, Any],
) -> Tuple[str, ...]:
    """Build a stable deduplication key for evidence."""

    evidence_id = str(
        evidence.get(
            "evidence_id",
            evidence.get("id", ""),
        )
        or ""
    ).strip()

    if evidence_id:
        return (
            "id",
            evidence_id,
        )

    return (
        "content",
        str(
            evidence.get("title", "")
            or ""
        ).strip(),
        str(
            evidence.get("text", "")
            or ""
        ).strip(),
        str(
            evidence.get("source_url", "")
            or ""
        ).strip(),
    )


def _merge_evidence(
    *evidence_groups: Sequence[
        Dict[str, Any]
    ],
) -> Tuple[Dict[str, Any], ...]:
    """Merge evidence records without duplicates."""

    merged_evidence: List[
        Dict[str, Any]
    ] = []

    seen_keys = set()

    for evidence_group in evidence_groups:
        for evidence in evidence_group:
            normalized_evidence = dict(evidence)
            key = _evidence_key(
                normalized_evidence
            )

            if key in seen_keys:
                continue

            seen_keys.add(key)
            merged_evidence.append(
                normalized_evidence
            )

    return tuple(merged_evidence)


def _safe_error_code(
    error: Exception,
) -> str:
    """Return a safe error identifier without provider details."""

    error_code = getattr(
        error,
        "error_code",
        None,
    )

    if error_code:
        return str(error_code)

    return type(error).__name__


class HybridVerifier:
    """Combine deterministic rules with an evidence-grounded LLM."""

    verifier_type = VerifierType.HYBRID

    def __init__(
        self,
        rule_verifier: Verifier,
        llm_verifier: Verifier,
        rule_short_circuit_confidence: float = 0.85,
        agreement_bonus: float = 0.05,
        single_verifier_discount: float = 0.90,
        llm_failure_discount: float = 0.85,
        conflict_confidence: float = 0.35,
    ) -> None:
        """Initialize the hybrid decision policy."""

        self._rule_verifier = rule_verifier
        self._llm_verifier = llm_verifier

        self._rule_short_circuit_confidence = (
            _normalize_probability(
                rule_short_circuit_confidence,
                "rule_short_circuit_confidence",
            )
        )

        self._agreement_bonus = (
            _normalize_probability(
                agreement_bonus,
                "agreement_bonus",
            )
        )

        self._single_verifier_discount = (
            _normalize_probability(
                single_verifier_discount,
                "single_verifier_discount",
            )
        )

        self._llm_failure_discount = (
            _normalize_probability(
                llm_failure_discount,
                "llm_failure_discount",
            )
        )

        self._conflict_confidence = (
            _normalize_probability(
                conflict_confidence,
                "conflict_confidence",
            )
        )

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        """Verify a claim using the hybrid policy."""

        rule_run = self._rule_verifier.verify(
            claim
        )

        if (
            _is_decisive(rule_run.result)
            and rule_run.result.confidence
            >= self._rule_short_circuit_confidence
        ):
            return self._build_rule_short_circuit(
                claim=claim,
                rule_run=rule_run,
            )

        try:
            llm_run = self._llm_verifier.verify(
                claim
            )
        except EXPECTED_LLM_ERRORS as error:
            return self._build_llm_fallback(
                claim=claim,
                rule_run=rule_run,
                error=error,
            )

        return self._combine_runs(
            claim=claim,
            rule_run=rule_run,
            llm_run=llm_run,
        )

    def _build_rule_short_circuit(
        self,
        claim: str,
        rule_run: VerificationRun,
    ) -> VerificationRun:
        """Return a high-confidence rule result without calling the LLM."""

        rule_result = rule_run.result

        result = VerificationResult(
            label=rule_result.label,
            confidence=rule_result.confidence,
            reason=(
                "The rule verifier produced a "
                "high-confidence decisive result, "
                "so the LLM judge was not called. "
                f"Rule reason: {rule_result.reason}"
            ),
            verifier_type=VerifierType.HYBRID,
            matched_evidence_ids=(
                rule_result.matched_evidence_ids
            ),
            matched_rule=(
                rule_result.matched_rule
            ),
            abstention_reason=None,
        )

        return VerificationRun(
            claim=claim,
            result=result,
            evidence=tuple(
                rule_run.evidence
            ),
        )

    def _build_llm_fallback(
        self,
        claim: str,
        rule_run: VerificationRun,
        error: Exception,
    ) -> VerificationRun:
        """Return a safe rule fallback after an expected LLM failure."""

        rule_result = rule_run.result
        error_code = _safe_error_code(
            error
        )

        if _is_decisive(rule_result):
            confidence = _clamp_confidence(
                rule_result.confidence
                * self._llm_failure_discount
            )

            reason = (
                "The LLM verifier was unavailable "
                f"with error code '{error_code}'. "
                "The hybrid verifier returned the "
                "rule result with reduced confidence. "
                f"Rule reason: {rule_result.reason}"
            )

            abstention_reason = None

        else:
            confidence = _clamp_confidence(
                rule_result.confidence
            )

            reason = (
                "The rule verifier was uncertain and "
                "the LLM verifier was unavailable "
                f"with error code '{error_code}'."
            )

            abstention_reason = (
                "llm_unavailable_and_rule_uncertain"
            )

        result = VerificationResult(
            label=rule_result.label,
            confidence=confidence,
            reason=reason,
            verifier_type=VerifierType.HYBRID,
            matched_evidence_ids=(
                rule_result.matched_evidence_ids
            ),
            matched_rule=(
                rule_result.matched_rule
            ),
            abstention_reason=(
                abstention_reason
            ),
        )

        return VerificationRun(
            claim=claim,
            result=result,
            evidence=tuple(
                rule_run.evidence
            ),
        )

    def _combine_runs(
        self,
        claim: str,
        rule_run: VerificationRun,
        llm_run: VerificationRun,
    ) -> VerificationRun:
        """Combine successful rule and LLM verification runs."""

        rule_result = rule_run.result
        llm_result = llm_run.result

        merged_evidence = _merge_evidence(
            rule_run.evidence,
            llm_run.evidence,
        )

        merged_evidence_ids = (
            _merge_evidence_ids(
                rule_result.matched_evidence_ids,
                llm_result.matched_evidence_ids,
            )
        )

        rule_decisive = _is_decisive(
            rule_result
        )

        llm_decisive = _is_decisive(
            llm_result
        )

        if (
            rule_decisive
            and llm_decisive
            and rule_result.label
            == llm_result.label
        ):
            confidence = _clamp_confidence(
                (
                    rule_result.confidence
                    + llm_result.confidence
                )
                / 2.0
                + self._agreement_bonus
            )

            result = VerificationResult(
                label=rule_result.label,
                confidence=confidence,
                reason=(
                    "The rule and LLM verifiers "
                    "reached the same decisive result. "
                    f"Rule reason: {rule_result.reason} "
                    f"LLM reason: {llm_result.reason}"
                ),
                verifier_type=VerifierType.HYBRID,
                matched_evidence_ids=(
                    merged_evidence_ids
                ),
                matched_rule=(
                    rule_result.matched_rule
                ),
                abstention_reason=None,
            )

            return VerificationRun(
                claim=claim,
                result=result,
                evidence=merged_evidence,
            )

        if (
            rule_decisive
            and llm_decisive
            and rule_result.label
            != llm_result.label
        ):
            result = VerificationResult(
                label=(
                    VerificationLabel.UNCERTAIN
                ),
                confidence=(
                    self._conflict_confidence
                ),
                reason=(
                    "The rule and LLM verifiers "
                    "produced conflicting decisive "
                    "results. The hybrid verifier "
                    "abstained rather than selecting "
                    "one result."
                ),
                verifier_type=VerifierType.HYBRID,
                matched_evidence_ids=(
                    merged_evidence_ids
                ),
                matched_rule=(
                    rule_result.matched_rule
                ),
                abstention_reason=(
                    "rule_llm_conflict"
                ),
            )

            return VerificationRun(
                claim=claim,
                result=result,
                evidence=merged_evidence,
            )

        if rule_decisive != llm_decisive:
            if rule_decisive:
                decisive_result = rule_result
                decisive_source = "rule"
                matched_rule = (
                    rule_result.matched_rule
                )
            else:
                decisive_result = llm_result
                decisive_source = "LLM"
                matched_rule = None

            confidence = _clamp_confidence(
                decisive_result.confidence
                * self._single_verifier_discount
            )

            result = VerificationResult(
                label=decisive_result.label,
                confidence=confidence,
                reason=(
                    f"Only the {decisive_source} "
                    "verifier produced a decisive "
                    "result; the other verifier "
                    "abstained. The decisive result "
                    "was retained with reduced "
                    "confidence. "
                    f"Reason: {decisive_result.reason}"
                ),
                verifier_type=VerifierType.HYBRID,
                matched_evidence_ids=(
                    merged_evidence_ids
                ),
                matched_rule=matched_rule,
                abstention_reason=None,
            )

            return VerificationRun(
                claim=claim,
                result=result,
                evidence=merged_evidence,
            )

        confidence = _clamp_confidence(
            max(
                rule_result.confidence,
                llm_result.confidence,
            )
        )

        result = VerificationResult(
            label=VerificationLabel.UNCERTAIN,
            confidence=confidence,
            reason=(
                "Both the rule and LLM verifiers "
                "were unable to reach a decisive "
                "result. "
                f"Rule reason: {rule_result.reason} "
                f"LLM reason: {llm_result.reason}"
            ),
            verifier_type=VerifierType.HYBRID,
            matched_evidence_ids=(
                merged_evidence_ids
            ),
            matched_rule=(
                rule_result.matched_rule
            ),
            abstention_reason=(
                "both_verifiers_uncertain"
            ),
        )

        return VerificationRun(
            claim=claim,
            result=result,
            evidence=merged_evidence,
        )
