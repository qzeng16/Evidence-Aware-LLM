"""Tests for the evidence embedding-cache lifecycle.

These tests do not load a real Sentence Transformer model. Small NumPy
arrays are used so cache behavior can be tested quickly and deterministically.
"""

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pytest

import layer0_verifier as verifier


def build_sample_evidence() -> List[Dict[str, str]]:
    """Return a small deterministic evidence corpus."""

    return [
        {
            "title": "First Evidence",
            "text": (
                "The first evidence statement is used to test "
                "embedding cache behavior."
            ),
        },
        {
            "title": "Second Evidence",
            "text": (
                "The second evidence statement is different from "
                "the first cache test statement."
            ),
        },
    ]


def build_fake_embeddings(
    evidence_list: List[Dict[str, str]],
    model: object,
) -> np.ndarray:
    """Return deterministic test embeddings."""

    del model

    values = np.arange(
        len(evidence_list) * 3,
        dtype=np.float32,
    )

    return values.reshape(
        len(evidence_list),
        3,
    )


@pytest.fixture
def isolated_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Dict[str, Path]:
    """Redirect verifier cache paths to a temporary directory."""

    cache_directory = tmp_path / "cache"
    embeddings_path = (
        cache_directory / "evidence_embeddings.npy"
    )
    metadata_path = (
        cache_directory / "evidence_embeddings_meta.json"
    )

    monkeypatch.setattr(
        verifier,
        "CACHE_DIR",
        cache_directory,
    )
    monkeypatch.setattr(
        verifier,
        "EMBEDDINGS_PATH",
        embeddings_path,
    )
    monkeypatch.setattr(
        verifier,
        "EMBEDDINGS_META_PATH",
        metadata_path,
    )
    monkeypatch.setattr(
        verifier,
        "MODEL_NAME",
        "test-embedding-model",
    )

    return {
        "cache_directory": cache_directory,
        "embeddings_path": embeddings_path,
        "metadata_path": metadata_path,
    }


def write_cache(
    evidence_list: List[Dict[str, str]],
    embeddings_path: Path,
    metadata_path: Path,
    model_name: str,
    embeddings: np.ndarray,
) -> None:
    """Write a test embedding cache and matching metadata."""

    embeddings_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.save(
        embeddings_path,
        embeddings,
    )

    metadata = {
        "model_name": model_name,
        "evidence_hash": verifier.compute_evidence_hash(
            evidence_list
        ),
        "evidence_count": len(evidence_list),
        "created_at": "2026-07-19T12:00:00",
    }

    metadata_path.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_cache_is_created_when_missing(
    isolated_cache: Dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """Missing cache files should be generated automatically."""

    evidence_list = build_sample_evidence()

    monkeypatch.setattr(
        verifier,
        "build_evidence_embeddings",
        build_fake_embeddings,
    )

    embeddings = verifier.get_or_build_evidence_embeddings(
        evidence_list,
        model=object(),
    )

    assert embeddings.shape == (2, 3)
    assert embeddings.dtype == np.float32

    assert isolated_cache["cache_directory"].exists()
    assert isolated_cache["embeddings_path"].exists()
    assert isolated_cache["metadata_path"].exists()

    saved_embeddings = np.load(
        isolated_cache["embeddings_path"]
    )

    assert np.array_equal(
        embeddings,
        saved_embeddings,
    )

    metadata = json.loads(
        isolated_cache["metadata_path"].read_text(
            encoding="utf-8"
        )
    )

    assert metadata["model_name"] == (
        "test-embedding-model"
    )
    assert metadata["evidence_count"] == 2
    assert metadata["evidence_hash"] == (
        verifier.compute_evidence_hash(evidence_list)
    )
    assert metadata["created_at"]


def test_valid_cache_is_reused_without_rebuilding(
    isolated_cache: Dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """A valid cache should be loaded without encoding again."""

    evidence_list = build_sample_evidence()

    cached_embeddings = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ],
        dtype=np.float32,
    )

    write_cache(
        evidence_list=evidence_list,
        embeddings_path=isolated_cache[
            "embeddings_path"
        ],
        metadata_path=isolated_cache["metadata_path"],
        model_name="test-embedding-model",
        embeddings=cached_embeddings,
    )

    def fail_if_rebuilt(
        evidence_records: List[Dict[str, str]],
        model: object,
    ) -> np.ndarray:
        del evidence_records
        del model

        raise AssertionError(
            "Valid embedding cache should not be rebuilt."
        )

    monkeypatch.setattr(
        verifier,
        "build_evidence_embeddings",
        fail_if_rebuilt,
    )

    loaded_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            evidence_list,
            model=object(),
        )
    )

    assert np.array_equal(
        loaded_embeddings,
        cached_embeddings,
    )


def test_cache_is_rebuilt_when_evidence_changes(
    isolated_cache: Dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """A changed corpus hash should invalidate the cache."""

    original_evidence = build_sample_evidence()

    original_embeddings = np.zeros(
        (2, 3),
        dtype=np.float32,
    )

    write_cache(
        evidence_list=original_evidence,
        embeddings_path=isolated_cache[
            "embeddings_path"
        ],
        metadata_path=isolated_cache["metadata_path"],
        model_name="test-embedding-model",
        embeddings=original_embeddings,
    )

    updated_evidence = original_evidence + [
        {
            "title": "Third Evidence",
            "text": (
                "A newly ingested evidence statement should "
                "invalidate the previous embedding cache."
            ),
        }
    ]

    build_calls = {"count": 0}

    def counted_builder(
        evidence_records: List[Dict[str, str]],
        model: object,
    ) -> np.ndarray:
        build_calls["count"] += 1

        return build_fake_embeddings(
            evidence_records,
            model,
        )

    monkeypatch.setattr(
        verifier,
        "build_evidence_embeddings",
        counted_builder,
    )

    rebuilt_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            updated_evidence,
            model=object(),
        )
    )

    assert build_calls["count"] == 1
    assert rebuilt_embeddings.shape == (3, 3)

    metadata = json.loads(
        isolated_cache["metadata_path"].read_text(
            encoding="utf-8"
        )
    )

    assert metadata["evidence_count"] == 3
    assert metadata["evidence_hash"] == (
        verifier.compute_evidence_hash(updated_evidence)
    )


def test_cache_is_rebuilt_when_model_changes(
    isolated_cache: Dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """A changed model name should invalidate the cache."""

    evidence_list = build_sample_evidence()

    old_embeddings = np.zeros(
        (2, 3),
        dtype=np.float32,
    )

    write_cache(
        evidence_list=evidence_list,
        embeddings_path=isolated_cache[
            "embeddings_path"
        ],
        metadata_path=isolated_cache["metadata_path"],
        model_name="old-embedding-model",
        embeddings=old_embeddings,
    )

    build_calls = {"count": 0}

    def counted_builder(
        evidence_records: List[Dict[str, str]],
        model: object,
    ) -> np.ndarray:
        build_calls["count"] += 1

        return build_fake_embeddings(
            evidence_records,
            model,
        )

    monkeypatch.setattr(
        verifier,
        "build_evidence_embeddings",
        counted_builder,
    )

    rebuilt_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            evidence_list,
            model=object(),
        )
    )

    assert build_calls["count"] == 1
    assert rebuilt_embeddings.shape == (2, 3)

    metadata = json.loads(
        isolated_cache["metadata_path"].read_text(
            encoding="utf-8"
        )
    )

    assert metadata["model_name"] == (
        "test-embedding-model"
    )


def test_corrupted_embedding_file_is_rebuilt(
    isolated_cache: Dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """A corrupted NumPy cache should be replaced automatically."""

    evidence_list = build_sample_evidence()

    isolated_cache["cache_directory"].mkdir(
        parents=True,
        exist_ok=True,
    )

    isolated_cache["embeddings_path"].write_text(
        "this is not a valid NumPy file",
        encoding="utf-8",
    )

    metadata = {
        "model_name": "test-embedding-model",
        "evidence_hash": verifier.compute_evidence_hash(
            evidence_list
        ),
        "evidence_count": len(evidence_list),
        "created_at": "2026-07-19T12:00:00",
    }

    isolated_cache["metadata_path"].write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    build_calls = {"count": 0}

    def counted_builder(
        evidence_records: List[Dict[str, str]],
        model: object,
    ) -> np.ndarray:
        build_calls["count"] += 1

        return build_fake_embeddings(
            evidence_records,
            model,
        )

    monkeypatch.setattr(
        verifier,
        "build_evidence_embeddings",
        counted_builder,
    )

    rebuilt_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            evidence_list,
            model=object(),
        )
    )

    assert build_calls["count"] == 1
    assert rebuilt_embeddings.shape == (2, 3)

    saved_embeddings = np.load(
        isolated_cache["embeddings_path"]
    )

    assert np.array_equal(
        rebuilt_embeddings,
        saved_embeddings,
    )
