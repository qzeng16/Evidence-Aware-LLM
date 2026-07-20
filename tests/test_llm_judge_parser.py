"""Tests for strict LLM judge response parsing."""

import json

import pytest

from app.llm_judge_parser import (
    EMPTY_RESPONSE_ERROR,
    INVALID_JSON_ERROR,
    INVALID_OUTPUT_ERROR,
    INVALID_TOP_LEVEL_ERROR,
    MARKDOWN_FENCE_ERROR,
    UNKNOWN_EVIDENCE_ERROR,
    LLMJudgeResponseParseError,
    parse_llm_judge_response,
)
from app.verification_result import (
    VerificationLabel,
)


def build_valid_payload():
    """Return one valid supported judge response."""

    return {
        "label": "Supported",
        "confidence": 0.84,
        "reason": (
            "Evidence rag-002 directly supports "
            "the claim."
        ),
        "evidence_ids": [
            "rag-002",
        ],
    }


def test_valid_json_response_is_parsed():
    """A valid standalone JSON object should be accepted."""

    raw_response = json.dumps(
        build_valid_payload()
    )

    output = parse_llm_judge_response(
        raw_response,
        available_evidence_ids=[
            "rag-002",
            "seed-002",
        ],
    )

    assert (
        output.label
        == VerificationLabel.SUPPORTED
    )
    assert output.confidence == 0.84
    assert output.evidence_ids == (
        "rag-002",
    )


def test_surrounding_whitespace_is_allowed():
    """Whitespace outside the JSON object is harmless."""

    raw_response = (
        "\n   "
        + json.dumps(build_valid_payload())
        + "   \n"
    )

    output = parse_llm_judge_response(
        raw_response,
        available_evidence_ids=[
            "rag-002",
        ],
    )

    assert output.label.value == "Supported"


def test_uncertain_response_without_evidence_ids_is_valid():
    """An uncertain result may abstain without citing evidence."""

    raw_response = json.dumps(
        {
            "label": "Uncertain",
            "confidence": 0.45,
            "reason": (
                "The supplied evidence is insufficient."
            ),
            "evidence_ids": [],
        }
    )

    output = parse_llm_judge_response(
        raw_response,
        available_evidence_ids=[
            "rag-002",
        ],
    )

    assert output.label.value == "Uncertain"
    assert output.evidence_ids == ()


def test_empty_response_is_rejected():
    """Blank model output should fail explicitly."""

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response("   ")

    assert (
        error_info.value.error_code
        == EMPTY_RESPONSE_ERROR
    )


def test_non_string_response_is_rejected():
    """The parser should accept text, not arbitrary objects."""

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            build_valid_payload()
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )


@pytest.mark.parametrize(
    "raw_response",
    [
        (
            "```json\n"
            '{"label":"Uncertain",'
            '"confidence":0.5,'
            '"reason":"Insufficient evidence.",'
            '"evidence_ids":[]}'
            "\n```"
        ),
        (
            "```\n"
            '{"label":"Uncertain",'
            '"confidence":0.5,'
            '"reason":"Insufficient evidence.",'
            '"evidence_ids":[]}'
            "\n```"
        ),
    ],
)
def test_markdown_code_fence_is_rejected(
    raw_response,
):
    """The model must return raw JSON without markdown."""

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            raw_response
        )

    assert (
        error_info.value.error_code
        == MARKDOWN_FENCE_ERROR
    )


@pytest.mark.parametrize(
    "raw_response",
    [
        (
            "Here is the result: "
            '{"label":"Uncertain",'
            '"confidence":0.5,'
            '"reason":"Insufficient evidence.",'
            '"evidence_ids":[]}'
        ),
        (
            '{"label":"Uncertain",'
            '"confidence":0.5,'
            '"reason":"Insufficient evidence.",'
            '"evidence_ids":[]}'
            "\nThis is my explanation."
        ),
        (
            '{"label":"Uncertain"}'
            '{"label":"Uncertain"}'
        ),
    ],
)
def test_surrounding_text_is_rejected(
    raw_response,
):
    """Only one standalone JSON object is allowed."""

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            raw_response
        )

    assert (
        error_info.value.error_code
        == INVALID_JSON_ERROR
    )


def test_malformed_json_is_rejected():
    """Invalid JSON syntax should fail clearly."""

    raw_response = (
        '{"label": "Supported", '
        '"confidence": 0.8,'
    )

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            raw_response
        )

    assert (
        error_info.value.error_code
        == INVALID_JSON_ERROR
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [
            {
                "label": "Uncertain",
                "confidence": 0.5,
                "reason": "Insufficient evidence.",
                "evidence_ids": [],
            }
        ],
        "Supported",
        1,
        None,
    ],
)
def test_non_object_top_level_json_is_rejected(
    payload,
):
    """The top-level JSON value must be an object."""

    raw_response = json.dumps(payload)

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            raw_response
        )

    assert (
        error_info.value.error_code
        == INVALID_TOP_LEVEL_ERROR
    )


def test_missing_field_is_rejected():
    """All required structured-output fields must exist."""

    payload = build_valid_payload()
    payload.pop("reason")

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
            ],
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )
    assert "missing fields" in str(
        error_info.value
    )


def test_extra_field_is_rejected():
    """Unexpected model-generated fields should fail."""

    payload = build_valid_payload()
    payload["analysis"] = (
        "This field is not allowed."
    )

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
            ],
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )
    assert "unexpected fields" in str(
        error_info.value
    )


def test_invalid_label_is_rejected():
    """The parser should reject unsupported labels."""

    payload = build_valid_payload()
    payload["label"] = "Mostly Supported"

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
            ],
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )
    assert "Invalid LLM judge label" in str(
        error_info.value
    )


@pytest.mark.parametrize(
    "confidence",
    [
        -0.01,
        1.01,
        "high",
    ],
)
def test_invalid_confidence_is_rejected(
    confidence,
):
    """Confidence must be numeric and between zero and one."""

    payload = build_valid_payload()
    payload["confidence"] = confidence

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
            ],
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )


def test_decisive_result_without_citation_is_rejected():
    """Supported and Refuted decisions require citations."""

    payload = build_valid_payload()
    payload["evidence_ids"] = []

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
            ],
        )

    assert (
        error_info.value.error_code
        == INVALID_OUTPUT_ERROR
    )
    assert "cite at least one evidence ID" in str(
        error_info.value
    )


def test_unknown_evidence_id_is_rejected():
    """The model cannot invent evidence citations."""

    payload = build_valid_payload()
    payload["evidence_ids"] = [
        "invented-999",
    ]

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        parse_llm_judge_response(
            json.dumps(payload),
            available_evidence_ids=[
                "rag-002",
                "seed-002",
            ],
        )

    assert (
        error_info.value.error_code
        == UNKNOWN_EVIDENCE_ERROR
    )
    assert "invented-999" in str(
        error_info.value
    )


def test_evidence_validation_can_be_deferred():
    """Provider parsing may run before evidence IDs are available."""

    payload = build_valid_payload()
    payload["evidence_ids"] = [
        "temporarily-unchecked",
    ]

    output = parse_llm_judge_response(
        json.dumps(payload),
        available_evidence_ids=None,
    )

    assert output.evidence_ids == (
        "temporarily-unchecked",
    )
