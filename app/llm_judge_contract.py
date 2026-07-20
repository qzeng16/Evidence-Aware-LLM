"""Structured output contract for the LLM judge.

The external model must return a small provider-independent JSON object.
This module validates that object before it enters the application.
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from app.verification_result import (
    VerificationLabel,
    VerificationResult,
    VerifierType,
)


class LLMJudgeOutputError(ValueError):
    """Raised when an LLM judge output is invalid."""


LLM_JUDGE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "label",
        "confidence",
        "reason",
        "evidence_ids",
    ],
    "properties": {
        "label": {
            "type": "string",
            "enum": [
                "Supported",
                "Refuted",
                "Uncertain",
            ],
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "reason": {
            "type": "string",
        },
        "evidence_ids": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
    },
}


def _normalize_label(
    value: Any,
) -> VerificationLabel:
    """Normalize and validate the decision label."""

    try:
        return VerificationLabel(value)
    except (TypeError, ValueError) as error:
        allowed_labels = ", ".join(
            label.value
            for label in VerificationLabel
        )

        raise LLMJudgeOutputError(
            f"Invalid LLM judge label '{value}'. "
            f"Allowed labels: {allowed_labels}"
        ) from error


def _normalize_confidence(
    value: Any,
) -> float:
    """Normalize and validate confidence."""

    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise LLMJudgeOutputError(
            "LLM judge confidence must be a number."
        ) from error

    if not 0.0 <= confidence <= 1.0:
        raise LLMJudgeOutputError(
            "LLM judge confidence must be between "
            "0.0 and 1.0."
        )

    return confidence


def _normalize_reason(
    value: Any,
) -> str:
    """Normalize and validate the decision explanation."""

    reason = str(value or "").strip()

    if not reason:
        raise LLMJudgeOutputError(
            "LLM judge reason cannot be empty."
        )

    return reason


def _normalize_evidence_ids(
    values: Iterable[Any],
) -> Tuple[str, ...]:
    """Normalize evidence IDs while preserving order."""

    if isinstance(values, str):
        raise LLMJudgeOutputError(
            "evidence_ids must be an array, "
            "not a single string."
        )

    normalized_ids = []
    seen_ids = set()

    try:
        raw_values = list(values)
    except TypeError as error:
        raise LLMJudgeOutputError(
            "evidence_ids must be an array."
        ) from error

    for value in raw_values:
        evidence_id = str(value).strip()

        if not evidence_id:
            raise LLMJudgeOutputError(
                "evidence_ids cannot contain "
                "blank values."
            )

        if evidence_id in seen_ids:
            continue

        seen_ids.add(evidence_id)
        normalized_ids.append(evidence_id)

    return tuple(normalized_ids)


@dataclass(frozen=True)
class LLMJudgeOutput:
    """Validated structured output produced by an LLM judge."""

    label: VerificationLabel
    confidence: float
    reason: str
    evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize and validate all output fields."""

        normalized_label = _normalize_label(
            self.label
        )
        normalized_confidence = (
            _normalize_confidence(
                self.confidence
            )
        )
        normalized_reason = _normalize_reason(
            self.reason
        )
        normalized_evidence_ids = (
            _normalize_evidence_ids(
                self.evidence_ids
            )
        )

        if (
            normalized_label
            in {
                VerificationLabel.SUPPORTED,
                VerificationLabel.REFUTED,
            }
            and not normalized_evidence_ids
        ):
            raise LLMJudgeOutputError(
                "Supported and Refuted outputs must "
                "cite at least one evidence ID."
            )

        object.__setattr__(
            self,
            "label",
            normalized_label,
        )
        object.__setattr__(
            self,
            "confidence",
            normalized_confidence,
        )
        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )
        object.__setattr__(
            self,
            "evidence_ids",
            normalized_evidence_ids,
        )

    def validate_evidence_ids(
        self,
        available_evidence_ids: Iterable[str],
    ) -> None:
        """Ensure cited IDs exist in the supplied evidence."""

        available_ids = {
            str(evidence_id).strip()
            for evidence_id in available_evidence_ids
            if str(evidence_id).strip()
        }

        unknown_ids = [
            evidence_id
            for evidence_id in self.evidence_ids
            if evidence_id not in available_ids
        ]

        if unknown_ids:
            raise LLMJudgeOutputError(
                "LLM judge cited unknown evidence IDs: "
                f"{unknown_ids}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize into a provider-independent dictionary."""

        return {
            "label": self.label.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence_ids": list(
                self.evidence_ids
            ),
        }

    def to_verification_result(
        self,
    ) -> VerificationResult:
        """Convert the LLM output into the shared result type."""

        abstention_reason = None

        if (
            self.label
            == VerificationLabel.UNCERTAIN
        ):
            abstention_reason = self.reason

        return VerificationResult(
            label=self.label,
            confidence=self.confidence,
            reason=self.reason,
            verifier_type=VerifierType.LLM,
            matched_evidence_ids=(
                self.evidence_ids
            ),
            matched_rule=None,
            abstention_reason=(
                abstention_reason
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "LLMJudgeOutput":
        """Build and validate output from parsed JSON."""

        if not isinstance(payload, Mapping):
            raise LLMJudgeOutputError(
                "LLM judge output must be a JSON object."
            )

        required_fields = {
            "label",
            "confidence",
            "reason",
            "evidence_ids",
        }

        missing_fields = (
            required_fields - set(payload)
        )

        if missing_fields:
            raise LLMJudgeOutputError(
                "LLM judge output is missing fields: "
                f"{sorted(missing_fields)}"
            )

        unexpected_fields = (
            set(payload) - required_fields
        )

        if unexpected_fields:
            raise LLMJudgeOutputError(
                "LLM judge output contains unexpected "
                f"fields: {sorted(unexpected_fields)}"
            )

        return cls(
            label=payload["label"],
            confidence=payload["confidence"],
            reason=payload["reason"],
            evidence_ids=tuple(
                payload["evidence_ids"]
            ),
        )
