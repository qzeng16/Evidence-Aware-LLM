"""Tests for evidence provenance metadata propagation."""

import csv
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from app.schemas import VerifyResponse
import layer0_verifier as verifier


FULL_CSV_FIELDS = [
    "evidence_id",
    "title",
    "text",
    "source_name",
    "source_type",
    "topic",
    "source_url",
    "published_at",
    "retrieved_at",
]


def build_metadata_record() -> Dict[str, str]:
    """Return a complete evidence record for tests."""

    return {
        "evidence_id": "rag-test-001",
        "title": "RAG Factuality Evidence",
        "text": (
            "Retrieval augmented generation can improve "
            "factual reliability by grounding generated "
            "answers in retrieved documents."
        ),
        "source_name": "Example research paper",
        "source_type": "paper",
        "topic": "retrieval augmented generation",
        "source_url": "https://example.com/paper",
        "published_at": "2024-01-15",
        "retrieved_at": "2026-07-19",
    }


def test_load_evidence_preserves_metadata(
    tmp_path: Path,
):
    """The CSV loader should preserve provenance fields."""

    csv_path = tmp_path / "evidence.csv"
    expected_record = build_metadata_record()

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FULL_CSV_FIELDS,
        )
        writer.writeheader()
        writer.writerow(expected_record)

    records = verifier.load_evidence(csv_path)

    assert len(records) == 1

    loaded_record = records[0]

    for field_name, expected_value in (
        expected_record.items()
    ):
        assert loaded_record[field_name] == expected_value


def test_load_evidence_supports_legacy_csv(
    tmp_path: Path,
):
    """Legacy title/text-only CSV files should remain valid."""

    csv_path = tmp_path / "legacy_evidence.csv"

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["title", "text"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "title": "Legacy Evidence",
                "text": (
                    "This legacy evidence contains enough "
                    "text for loader compatibility testing."
                ),
            }
        )

    records = verifier.load_evidence(csv_path)

    assert len(records) == 1
    assert records[0]["title"] == "Legacy Evidence"

    for field_name in verifier.EVIDENCE_METADATA_FIELDS:
        assert records[0][field_name] == ""


class FakeEmbeddingModel:
    """Return a fixed claim embedding for retrieval tests."""

    def encode(
        self,
        texts: List[str],
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        del texts

        assert convert_to_numpy is True

        return np.array(
            [[1.0, 0.0]],
            dtype=np.float32,
        )


def test_search_evidence_returns_metadata():
    """Retrieved evidence should include provenance metadata."""

    evidence_record = build_metadata_record()

    evidence_embeddings = np.array(
        [[1.0, 0.0]],
        dtype=np.float32,
    )

    results = verifier.search_evidence(
        claim=(
            "Retrieval augmented generation can improve "
            "factual reliability."
        ),
        evidence_list=[evidence_record],
        model=FakeEmbeddingModel(),
        evidence_embeddings=evidence_embeddings,
        initial_top_k=1,
        final_top_k=1,
        min_score=0.0,
    )

    assert len(results) == 1

    result = results[0]

    for field_name in verifier.EVIDENCE_METADATA_FIELDS:
        assert result[field_name] == (
            evidence_record[field_name]
        )

    assert "score" in result
    assert "embedding_score" in result
    assert "keyword_score" in result


def test_verify_response_preserves_metadata():
    """Pydantic response validation should retain nested metadata."""

    evidence_item = build_metadata_record()

    evidence_item.update(
        {
            "score": 0.91,
            "embedding_score": 0.92,
            "keyword_score": 0.88,
        }
    )

    result = {
        "claim": (
            "Retrieval augmented generation can improve "
            "factual reliability."
        ),
        "label": "Supported",
        "confidence": 0.86,
        "evidence": [evidence_item],
        "matched_rule": (
            "supports_rag_improves_reliability"
        ),
        "abstention_reason": None,
    }

    response = verifier.build_success_response(result)
    validated_response = VerifyResponse(**response)

    if hasattr(validated_response, "model_dump"):
        serialized = validated_response.model_dump()
    else:
        serialized = validated_response.dict()

    returned_item = serialized["data"]["evidence"][0]

    assert returned_item["evidence_id"] == (
        "rag-test-001"
    )
    assert returned_item["source_name"] == (
        "Example research paper"
    )
    assert returned_item["source_type"] == "paper"
    assert returned_item["source_url"] == (
        "https://example.com/paper"
    )
    assert returned_item["topic"] == (
        "retrieval augmented generation"
    )
