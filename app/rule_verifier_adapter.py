"""Adapter from the legacy rule-verifier output to VerificationResult."""

from typing import Any, Dict, Iterable, Tuple

from app.verification_result import (
    VerificationLabel,
    VerificationResult,
    VerificationResultError,
    VerifierType,
)


def _normalize_evidence_ids(
    values: Any,
) -> Tuple[str, ...]:
    """Normalize evidence IDs from a legacy result."""

    if values is None:
        return ()

    if isinstance(values, str):
        raw_values: Iterable[Any] = [values]
    else:
        try:
            raw_values = list(values)
        except TypeError:
            raw_values = []

    normalized_ids = []
    seen_ids = set()

    for value in raw_values:
        evidence_id = str(value).strip()

        if not evidence_id:
            continue

        if evidence_id in seen_ids:
            continue

        seen_ids.add(evidence_id)
        normalized_ids.append(evidence_id)

    return tuple(normalized_ids)


def _build_rule_reason(
    label: VerificationLabel,
    matched_rule: Any,
    abstention_reason: Any,
) -> str:
    """Create a readable explanation for a rule result."""

    normalized_rule = str(
        matched_rule or ""
    ).strip()

    normalized_abstention_reason = str(
        abstention_reason or ""
    ).strip()

    if label == VerificationLabel.UNCERTAIN:
        if normalized_abstention_reason:
            return normalized_abstention_reason

        return (
            "The rule-based verifier could not determine "
            "whether the evidence supports or refutes the claim."
        )

    if label == VerificationLabel.SUPPORTED:
        if normalized_rule:
            return (
                f"Rule '{normalized_rule}' matched retrieved "
                "evidence that supports the claim."
            )

        return (
            "The rule-based verifier found retrieved evidence "
            "that supports the claim."
        )

    if normalized_rule:
        return (
            f"Rule '{normalized_rule}' matched retrieved "
            "evidence that contradicts the claim."
        )

    return (
        "The rule-based verifier found retrieved evidence "
        "that contradicts the claim."
    )


def build_rule_verification_result(
    legacy_result: Dict[str, Any],
) -> VerificationResult:
    """Convert a legacy rule result into VerificationResult."""

    required_fields = {
        "label",
        "confidence",
    }

    missing_fields = (
        required_fields - set(legacy_result)
    )

    if missing_fields:
        raise VerificationResultError(
            "Legacy rule result is missing fields: "
            f"{sorted(missing_fields)}"
        )

    label_value = legacy_result["label"]

    try:
        label = VerificationLabel(label_value)
    except (TypeError, ValueError) as error:
        raise VerificationResultError(
            f"Invalid rule-verifier label '{label_value}'."
        ) from error

    matched_rule = legacy_result.get(
        "matched_rule"
    )

    abstention_reason = legacy_result.get(
        "abstention_reason"
    )

    matched_evidence_ids = _normalize_evidence_ids(
        legacy_result.get(
            "matched_evidence_ids",
            [],
        )
    )

    reason = _build_rule_reason(
        label=label,
        matched_rule=matched_rule,
        abstention_reason=abstention_reason,
    )

    return VerificationResult(
        label=label,
        confidence=legacy_result["confidence"],
        reason=reason,
        verifier_type=VerifierType.RULE,
        matched_evidence_ids=matched_evidence_ids,
        matched_rule=matched_rule,
        abstention_reason=abstention_reason,
    )
