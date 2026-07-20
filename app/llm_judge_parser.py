"""Strict parser for LLM judge responses.

The parser accepts exactly one JSON object and validates it against the
provider-independent LLMJudgeOutput contract.

It intentionally rejects markdown code fences and surrounding commentary.
Structured-output failures should remain visible so later layers can apply
controlled retries or rule-based fallback.
"""

import json
from typing import Iterable, Optional

from app.llm_judge_contract import (
    LLMJudgeOutput,
    LLMJudgeOutputError,
)


EMPTY_RESPONSE_ERROR = "empty_response"
MARKDOWN_FENCE_ERROR = "markdown_code_fence"
INVALID_JSON_ERROR = "invalid_json"
INVALID_TOP_LEVEL_ERROR = "invalid_top_level"
INVALID_OUTPUT_ERROR = "invalid_output"
UNKNOWN_EVIDENCE_ERROR = "unknown_evidence_id"


class LLMJudgeResponseParseError(ValueError):
    """Raised when a raw LLM response cannot be safely parsed."""

    def __init__(
        self,
        message: str,
        error_code: str,
    ) -> None:
        super().__init__(message)

        self.error_code = error_code


def _contains_markdown_code_fence(
    response_text: str,
) -> bool:
    """Return whether the response contains a markdown code fence."""

    return "```" in response_text


def _parse_json_object(
    response_text: str,
) -> dict:
    """Parse exactly one top-level JSON object."""

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise LLMJudgeResponseParseError(
            (
                "LLM judge response is not valid standalone JSON: "
                f"{error.msg} at line {error.lineno}, "
                f"column {error.colno}."
            ),
            error_code=INVALID_JSON_ERROR,
        ) from error

    if not isinstance(payload, dict):
        raise LLMJudgeResponseParseError(
            "LLM judge response must be one top-level JSON object.",
            error_code=INVALID_TOP_LEVEL_ERROR,
        )

    return payload


def parse_llm_judge_response(
    raw_response: str,
    available_evidence_ids: Optional[
        Iterable[str]
    ] = None,
) -> LLMJudgeOutput:
    """Parse and validate one raw LLM judge response.

    Args:
        raw_response: Raw text returned by the model.
        available_evidence_ids: Evidence IDs supplied to the model.
            When provided, every cited ID must exist in this collection.

    Returns:
        A validated LLMJudgeOutput.

    Raises:
        LLMJudgeResponseParseError: If parsing or validation fails.
    """

    if not isinstance(raw_response, str):
        raise LLMJudgeResponseParseError(
            "LLM judge response must be a string.",
            error_code=INVALID_OUTPUT_ERROR,
        )

    normalized_response = raw_response.strip()

    if not normalized_response:
        raise LLMJudgeResponseParseError(
            "LLM judge response cannot be empty.",
            error_code=EMPTY_RESPONSE_ERROR,
        )

    if _contains_markdown_code_fence(
        normalized_response
    ):
        raise LLMJudgeResponseParseError(
            (
                "LLM judge response must not contain "
                "markdown code fences."
            ),
            error_code=MARKDOWN_FENCE_ERROR,
        )

    payload = _parse_json_object(
        normalized_response
    )

    try:
        output = LLMJudgeOutput.from_dict(
            payload
        )
    except LLMJudgeOutputError as error:
        raise LLMJudgeResponseParseError(
            f"Invalid LLM judge output: {error}",
            error_code=INVALID_OUTPUT_ERROR,
        ) from error

    if available_evidence_ids is not None:
        try:
            output.validate_evidence_ids(
                available_evidence_ids
            )
        except LLMJudgeOutputError as error:
            raise LLMJudgeResponseParseError(
                f"Invalid evidence citation: {error}",
                error_code=UNKNOWN_EVIDENCE_ERROR,
            ) from error

    return output
