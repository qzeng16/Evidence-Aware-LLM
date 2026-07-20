import pytest
from sentence_transformers import SentenceTransformer

import layer0_verifier as verifier


@pytest.fixture(scope="session")
def verifier_resources():
    evidence_db = verifier.load_evidence(verifier.DATA_PATH)
    verification_rules = verifier.load_rules(verifier.RULES_PATH)

    model = SentenceTransformer(verifier.MODEL_NAME)

    evidence_embeddings = verifier.get_or_build_evidence_embeddings(
        evidence_db,
        model
    )

    return {
        "evidence_db": evidence_db,
        "verification_rules": verification_rules,
        "model": model,
        "evidence_embeddings": evidence_embeddings
    }


def test_validate_claim_empty():
    is_valid, error_message = verifier.validate_claim("")

    assert is_valid is False
    assert error_message == "Claim cannot be empty."


def test_validate_claim_too_short():
    is_valid, error_message = verifier.validate_claim("1")

    assert is_valid is False
    assert error_message == "Claim is too short to verify."


def test_validate_claim_valid():
    is_valid, error_message = verifier.validate_claim(
        "Retrieval augmented generation can improve factual reliability."
    )

    assert is_valid is True
    assert error_message == ""


def test_supported_claim(verifier_resources):
    result = verifier.verify_claim(
        claim="Retrieval augmented generation can improve factual reliability.",
        evidence_db=verifier_resources["evidence_db"],
        verification_rules=verifier_resources["verification_rules"],
        model=verifier_resources["model"],
        evidence_embeddings=verifier_resources["evidence_embeddings"]
    )

    assert result["label"] == "Supported"
    assert result["confidence"] > 0.5
    assert len(result["evidence"]) > 0


def test_refuted_claim(verifier_resources):
    result = verifier.verify_claim(
        claim="Retrieval augmented generation cannot improve factual reliability.",
        evidence_db=verifier_resources["evidence_db"],
        verification_rules=verifier_resources["verification_rules"],
        model=verifier_resources["model"],
        evidence_embeddings=verifier_resources["evidence_embeddings"]
    )

    assert result["label"] == "Refuted"
    assert result["confidence"] > 0.5
    assert len(result["evidence"]) > 0


def test_uncertain_claim(verifier_resources):
    result = verifier.verify_claim(
        claim="Do bananas improve AI model reliability?",
        evidence_db=verifier_resources["evidence_db"],
        verification_rules=verifier_resources["verification_rules"],
        model=verifier_resources["model"],
        evidence_embeddings=verifier_resources["evidence_embeddings"]
    )

    assert result["label"] == "Uncertain"
    assert result["confidence"] <= 0.5
    assert result["abstention_reason"] is not None


def test_success_response_structure():
    result = {
        "claim": "Test claim",
        "label": "Supported",
        "confidence": 0.8,
        "evidence": [],
        "matched_rule": "test_rule",
        "abstention_reason": None
    }

    response = verifier.build_success_response(result)

    assert response["status"] == "success"
    assert "timestamp" in response
    assert response["data"]["claim"] == "Test claim"
    assert response["data"]["prediction"]["label"] == "Supported"
    assert response["data"]["prediction"]["confidence"] == 0.8
    assert "metadata" in response


def test_error_response_structure():
    response = verifier.build_error_response("Something went wrong.")

    assert response["status"] == "error"
    assert "timestamp" in response
    assert response["error"]["message"] == "Something went wrong."


@pytest.mark.parametrize(
    "claim, expected_label, expected_rule",
    [
        (
            (
                "Retrieval augmented generation can improve "
                "factual reliability."
            ),
            "Supported",
            "supports_rag_improves_reliability",
        ),
        (
            (
                "Retrieval augmented generation cannot improve "
                "factual reliability."
            ),
            "Refuted",
            "negates_rag_improves_reliability",
        ),
    ],
)
def test_verify_claim_checks_multiple_evidence_candidates(
    monkeypatch,
    claim,
    expected_label,
    expected_rule,
):
    """A rule match in lower-ranked evidence should still be used."""

    retrieved_evidence = [
        {
            "title": (
                "RAG Improved Factuality in Evaluated "
                "Generation Tasks"
            ),
            "text": (
                "In the original RAG experiments, "
                "retrieval-augmented models generated more "
                "factual language than a parametric-only "
                "sequence-to-sequence baseline."
            ),
            "embedding_score": 0.72,
            "keyword_score": 0.57,
            "score": 0.69,
        },
        {
            "title": "Retrieval Augmented Generation",
            "text": (
                "RAG can improve factual reliability by "
                "grounding answers in retrieved documents."
            ),
            "embedding_score": 0.63,
            "keyword_score": 0.43,
            "score": 0.61,
        },
    ]

    def fake_search_evidence(**kwargs):
        del kwargs
        return retrieved_evidence

    monkeypatch.setattr(
        verifier,
        "search_evidence",
        fake_search_evidence,
    )

    result = verifier.verify_claim(
        claim=claim,
        evidence_db=[],
        verification_rules=[],
        model=object(),
        evidence_embeddings=None,
    )

    assert result["label"] == expected_label
    assert result["matched_rule"] == expected_rule
    assert result["abstention_reason"] is None
    assert len(result["evidence"]) == 2

