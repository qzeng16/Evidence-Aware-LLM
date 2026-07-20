"""Force a safe rebuild of the evidence embedding cache.

The script:

1. Loads and validates the runtime evidence corpus.
2. Temporarily backs up the existing embedding cache.
3. Removes the current cache files.
4. Loads the configured sentence-transformer model.
5. Rebuilds the embeddings and metadata.
6. Validates the generated files.
7. Restores the previous cache if rebuilding fails.

Example:

    python3 scripts/rebuild_embeddings.py
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import layer0_verifier as verifier


class EmbeddingRebuildError(Exception):
    """Raised when the embedding cache cannot be safely rebuilt."""


def get_cache_paths() -> List[Path]:
    """Return all generated embedding cache paths."""

    return [
        verifier.EMBEDDINGS_PATH,
        verifier.EMBEDDINGS_META_PATH,
    ]


def backup_existing_cache(
    backup_directory: Path,
) -> Dict[Path, Path]:
    """Copy existing cache files into a temporary backup directory."""

    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    backups = {}

    for cache_path in get_cache_paths():
        if not cache_path.exists():
            continue

        backup_path = backup_directory / cache_path.name

        shutil.copy2(
            str(cache_path),
            str(backup_path),
        )

        backups[cache_path] = backup_path

    return backups


def remove_current_cache() -> None:
    """Remove the current generated cache files."""

    for cache_path in get_cache_paths():
        if cache_path.exists():
            cache_path.unlink()


def restore_previous_cache(
    backups: Dict[Path, Path],
) -> None:
    """Restore cache files saved before a failed rebuild."""

    remove_current_cache()

    if not backups:
        return

    verifier.CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for destination_path, backup_path in backups.items():
        shutil.copy2(
            str(backup_path),
            str(destination_path),
        )


def load_cache_metadata(
    metadata_path: Path,
) -> Dict[str, Any]:
    """Load and validate the embedding metadata JSON object."""

    if not metadata_path.exists():
        raise EmbeddingRebuildError(
            f"Embedding metadata was not created: {metadata_path}"
        )

    try:
        with metadata_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            metadata = json.load(file)
    except json.JSONDecodeError as error:
        raise EmbeddingRebuildError(
            f"Embedding metadata is not valid JSON: {error}"
        )

    if not isinstance(metadata, dict):
        raise EmbeddingRebuildError(
            "Embedding metadata must contain a JSON object."
        )

    return metadata


def validate_rebuilt_cache(
    evidence_list: List[Dict[str, str]],
    generated_embeddings: np.ndarray,
) -> Dict[str, Any]:
    """Validate generated embeddings and metadata."""

    if not verifier.EMBEDDINGS_PATH.exists():
        raise EmbeddingRebuildError(
            "Embedding array file was not created."
        )

    saved_embeddings = np.load(
        verifier.EMBEDDINGS_PATH
    )

    if saved_embeddings.ndim != 2:
        raise EmbeddingRebuildError(
            "Embedding array must have exactly two dimensions."
        )

    if saved_embeddings.shape[0] != len(evidence_list):
        raise EmbeddingRebuildError(
            "Embedding row count does not match evidence count: "
            f"{saved_embeddings.shape[0]} embeddings for "
            f"{len(evidence_list)} evidence records."
        )

    if saved_embeddings.shape[1] <= 0:
        raise EmbeddingRebuildError(
            "Embedding dimension must be greater than zero."
        )

    if generated_embeddings.shape != saved_embeddings.shape:
        raise EmbeddingRebuildError(
            "Returned embeddings and saved embeddings have "
            "different shapes."
        )

    if not np.isfinite(saved_embeddings).all():
        raise EmbeddingRebuildError(
            "Embedding array contains NaN or infinite values."
        )

    metadata = load_cache_metadata(
        verifier.EMBEDDINGS_META_PATH
    )

    expected_hash = verifier.compute_evidence_hash(
        evidence_list
    )

    if metadata.get("model_name") != verifier.MODEL_NAME:
        raise EmbeddingRebuildError(
            "Metadata model_name does not match the configured "
            "embedding model."
        )

    if metadata.get("evidence_hash") != expected_hash:
        raise EmbeddingRebuildError(
            "Metadata evidence_hash does not match the corpus."
        )

    if metadata.get("evidence_count") != len(evidence_list):
        raise EmbeddingRebuildError(
            "Metadata evidence_count does not match the corpus."
        )

    if not metadata.get("created_at"):
        raise EmbeddingRebuildError(
            "Metadata is missing created_at."
        )

    return {
        "evidence_count": len(evidence_list),
        "embedding_shape": list(saved_embeddings.shape),
        "embedding_dtype": str(saved_embeddings.dtype),
        "model_name": metadata["model_name"],
        "evidence_hash": metadata["evidence_hash"],
        "created_at": metadata["created_at"],
    }


def print_summary(
    summary: Dict[str, Any],
    elapsed_seconds: float,
) -> None:
    """Print a human-readable rebuild summary."""

    print()
    print("Embedding rebuild summary")
    print("-------------------------")
    print(
        "Evidence records: "
        f"{summary['evidence_count']}"
    )
    print(
        "Embedding shape: "
        f"{tuple(summary['embedding_shape'])}"
    )
    print(
        "Embedding dtype: "
        f"{summary['embedding_dtype']}"
    )
    print(f"Model: {summary['model_name']}")
    print(f"Evidence hash: {summary['evidence_hash']}")
    print(f"Created at: {summary['created_at']}")
    print(f"Elapsed seconds: {elapsed_seconds:.2f}")
    print(f"Cache directory: {verifier.CACHE_DIR}")


def rebuild_embeddings() -> Dict[str, Any]:
    """Force a safe embedding-cache rebuild."""

    print(f"Loading evidence corpus: {verifier.DATA_PATH}")
    evidence_list = verifier.load_evidence(
        verifier.DATA_PATH
    )

    if not evidence_list:
        raise EmbeddingRebuildError(
            "The evidence corpus is empty."
        )

    print(
        f"Loaded {len(evidence_list)} evidence records."
    )

    with tempfile.TemporaryDirectory(
        prefix="evidence-embedding-backup-"
    ) as temporary_directory:
        backup_directory = Path(temporary_directory)

        backups = backup_existing_cache(
            backup_directory
        )

        if backups:
            print(
                f"Backed up {len(backups)} existing "
                "cache file(s)."
            )
        else:
            print("No existing cache files required backup.")

        try:
            remove_current_cache()

            print(
                f"Loading embedding model: "
                f"{verifier.MODEL_NAME}"
            )
            model = SentenceTransformer(
                verifier.MODEL_NAME
            )

            print("Rebuilding evidence embeddings...")
            generated_embeddings = (
                verifier.get_or_build_evidence_embeddings(
                    evidence_list,
                    model,
                )
            )

            print("Validating rebuilt cache...")
            summary = validate_rebuilt_cache(
                evidence_list,
                generated_embeddings,
            )

        except Exception as error:
            print(
                "Embedding rebuild failed. "
                "Restoring previous cache...",
                file=sys.stderr,
            )

            restore_previous_cache(backups)

            if isinstance(error, EmbeddingRebuildError):
                raise

            raise EmbeddingRebuildError(str(error))

    return summary


def main() -> int:
    """Run the embedding cache rebuild command."""

    started_at = time.perf_counter()

    try:
        summary = rebuild_embeddings()
    except EmbeddingRebuildError as error:
        print(
            f"Embedding rebuild failed: {error}",
            file=sys.stderr,
        )
        return 1

    elapsed_seconds = time.perf_counter() - started_at

    print_summary(
        summary=summary,
        elapsed_seconds=elapsed_seconds,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
