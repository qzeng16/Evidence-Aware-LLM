import csv
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


DATA_DIR = Path(__file__).parent / "data"

DATA_PATH = DATA_DIR / "evidence.csv"
RULES_PATH = DATA_DIR / "rules.json"

CACHE_DIR = DATA_DIR / "cache"
EMBEDDINGS_PATH = CACHE_DIR / "evidence_embeddings.npy"
EMBEDDINGS_META_PATH = CACHE_DIR / "evidence_embeddings_meta.json"

LOG_DIR = Path(__file__).parent / "logs"
LOG_PATH = LOG_DIR / "verification_logs.jsonl"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

EVIDENCE_METADATA_FIELDS = (
    "evidence_id",
    "source_name",
    "source_type",
    "topic",
    "source_url",
    "published_at",
    "retrieved_at",
)

MIN_FINAL_SCORE_FOR_VERIFICATION = 0.45
MIN_EMBEDDING_SCORE_FOR_VERIFICATION = 0.40
MIN_KEYWORD_SCORE_FOR_VERIFICATION = 0.20


def load_evidence(
    file_path: Path
) -> List[Dict[str, str]]:
    """Load the runtime evidence corpus.

    The title and text columns remain required. Provenance metadata fields
    are optional so legacy two-column evidence CSV files remain compatible.
    Missing optional values are represented as empty strings.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"Evidence file not found: {file_path}"
        )

    evidence_list = []

    with open(
        file_path,
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("evidence.csv is empty.")

        required_columns = {"title", "text"}
        missing_columns = (
            required_columns - set(reader.fieldnames)
        )

        if missing_columns:
            raise ValueError(
                "evidence.csv is missing columns: "
                f"{missing_columns}"
            )

        for row in reader:
            title = (row.get("title") or "").strip()
            text = (row.get("text") or "").strip()

            if not title or not text:
                continue

            evidence_record = {
                "title": title,
                "text": text,
            }

            for field_name in EVIDENCE_METADATA_FIELDS:
                evidence_record[field_name] = (
                    row.get(field_name) or ""
                ).strip()

            evidence_list.append(evidence_record)

    if not evidence_list:
        raise ValueError(
            "No valid evidence found in evidence.csv."
        )

    return evidence_list

def load_rules(file_path: Path) -> List[Dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Rules file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            rules = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON format in rules.json: {error}")

    if not isinstance(rules, list):
        raise ValueError("rules.json must contain a list of rules.")

    return rules


def validate_claim(claim: str) -> Tuple[bool, str]:
    if not claim.strip():
        return False, "Claim cannot be empty."

    if len(claim.strip()) < 5:
        return False, "Claim is too short to verify."

    if len(claim.strip()) > 500:
        return False, "Claim is too long. Please keep it under 500 characters."

    return True, ""


def normalize_text(text: str) -> str:
    return text.lower().strip()


def tokenize(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def compute_keyword_overlap(claim: str, evidence_text: str) -> float:
    claim_tokens = tokenize(claim)
    evidence_tokens = tokenize(evidence_text)

    if not claim_tokens:
        return 0.0

    overlap = claim_tokens.intersection(evidence_tokens)
    return len(overlap) / len(claim_tokens)


def compute_evidence_hash(evidence_list: List[Dict[str, str]]) -> str:
    combined_text = ""

    for item in evidence_list:
        combined_text += item["title"] + "||" + item["text"] + "\n"

    return hashlib.sha256(combined_text.encode("utf-8")).hexdigest()


def build_evidence_embeddings(
    evidence_list: List[Dict[str, str]],
    model: SentenceTransformer
) -> np.ndarray:
    evidence_texts = [item["text"] for item in evidence_list]
    embeddings = model.encode(evidence_texts, convert_to_numpy=True)
    return embeddings


def get_or_build_evidence_embeddings(
    evidence_list: List[Dict[str, str]],
    model: SentenceTransformer
) -> np.ndarray:
    evidence_hash = compute_evidence_hash(evidence_list)

    if EMBEDDINGS_PATH.exists() and EMBEDDINGS_META_PATH.exists():
        try:
            with open(EMBEDDINGS_META_PATH, "r", encoding="utf-8") as file:
                metadata = json.load(file)

            cache_is_valid = (
                metadata.get("model_name") == MODEL_NAME
                and metadata.get("evidence_hash") == evidence_hash
                and metadata.get("evidence_count") == len(evidence_list)
            )

            if cache_is_valid:
                print("Loading cached evidence embeddings...")
                return np.load(EMBEDDINGS_PATH)

        except Exception:
            print("Embedding cache is invalid. Rebuilding embeddings...")

    print("Building evidence embeddings...")
    embeddings = build_evidence_embeddings(evidence_list, model)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    np.save(EMBEDDINGS_PATH, embeddings)

    metadata = {
        "model_name": MODEL_NAME,
        "evidence_hash": evidence_hash,
        "evidence_count": len(evidence_list),
        "created_at": datetime.now().isoformat()
    }

    with open(EMBEDDINGS_META_PATH, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)

    return embeddings


def search_evidence(
    claim: str,
    evidence_list: List[Dict[str, str]],
    model: SentenceTransformer,
    evidence_embeddings: np.ndarray,
    initial_top_k: int = 4,
    final_top_k: int = 2,
    min_score: float = 0.20
) -> List[Dict]:
    claim_embedding = model.encode([claim], convert_to_numpy=True)

    embedding_scores = cosine_similarity(claim_embedding, evidence_embeddings)[0]
    ranked_indices = np.argsort(embedding_scores)[::-1]

    candidates = []

    for index in ranked_indices[:initial_top_k]:
        embedding_score = float(embedding_scores[index])

        if embedding_score < min_score:
            continue

        evidence = evidence_list[index]
        keyword_score = compute_keyword_overlap(claim, evidence["text"])

        final_score = 0.8 * embedding_score + 0.2 * keyword_score

        candidate = {
            "title": evidence["title"],
            "text": evidence["text"],
        }

        for field_name in EVIDENCE_METADATA_FIELDS:
            candidate[field_name] = evidence.get(
                field_name,
                "",
            )

        candidate.update({
            "score": round(final_score, 4),
            "embedding_score": round(
                embedding_score,
                4,
            ),
            "keyword_score": round(
                keyword_score,
                4,
            ),
        })

        candidates.append(candidate)

    reranked_results = sorted(
        candidates,
        key=lambda item: item["score"],
        reverse=True
    )

    return reranked_results[:final_top_k]


def has_scope_mismatch(claim: str, evidence_text: str) -> bool:
    claim_text = normalize_text(claim)
    evidence = normalize_text(evidence_text)

    scope_terms = [
        "banana", "bananas",
        "coffee",
        "dental", "diagnosis",
        "biology",
        "graph neural networks",
        "transformers"
    ]

    for term in scope_terms:
        if term in claim_text and term not in evidence:
            return True

    return False


def has_unsupported_absolute_claim(claim: str, evidence_text: str) -> bool:
    claim_text = normalize_text(claim)
    evidence = normalize_text(evidence_text)

    absolute_patterns = [
        "guarantee",
        "every",
        "eliminate all",
        "all ai errors",
        "all scientific reasoning"
    ]

    for pattern in absolute_patterns:
        if pattern in claim_text and pattern not in evidence:
            return True

    return False


def infer_label_from_claim_and_evidence(
    claim: str,
    evidence_text: str
) -> Tuple[str, float, Optional[str]]:
    claim_text = normalize_text(claim)
    evidence = normalize_text(evidence_text)

    # Case 1: small biased datasets are not always reliable
    if "not always reliable" in evidence:
        if "not always reliable" in claim_text:
            return "Supported", 0.88, "same_direction_not_always_reliable"

        if "always reliable" in claim_text or "always make ai models reliable" in claim_text:
            return "Refuted", 0.86, "contradicts_not_always_reliable"

    # Case 2: RAG improves factual reliability
    if "improve factual reliability" in evidence:
        if "cannot improve factual reliability" in claim_text:
            return "Refuted", 0.86, "negates_rag_improves_reliability"

        if "does not improve factual reliability" in claim_text:
            return "Refuted", 0.86, "negates_rag_improves_reliability"

        if "retrieval augmented generation" in claim_text and "improve factual reliability" in claim_text:
            return "Supported", 0.86, "supports_rag_improves_reliability"

        if "grounding answers" in claim_text and "improve factual reliability" in claim_text:
            return "Supported", 0.84, "supports_grounding_improves_reliability"

    # Case 3: LLMs can generate unsupported scientific claims
    if "generate unsupported scientific claims" in evidence:
        if "can generate unsupported scientific claims" in claim_text:
            return "Supported", 0.84, "supports_llm_can_generate_unsupported_claims"

        if "never generate unsupported scientific claims" in claim_text:
            return "Refuted", 0.86, "negates_llm_can_generate_unsupported_claims"

        if "always provide accurate scientific claims" in claim_text:
            return "Refuted", 0.84, "contradicts_unsupported_scientific_claims"

    # Case 4: human oversight is important
    if "human oversight is important" in evidence:
        if "human oversight is not important" in claim_text:
            return "Refuted", 0.86, "negates_human_oversight_importance"

        if "human oversight" in claim_text and "important" in claim_text:
            return "Supported", 0.84, "supports_human_oversight_importance"

        if "human supervision" in claim_text and "important" in claim_text:
            return "Supported", 0.82, "supports_human_supervision_importance"

    return "Uncertain", 0.5, None


def should_abstain(best_evidence: Dict, claim: str) -> Tuple[bool, str]:
    final_score = best_evidence.get("score", 0.0)
    embedding_score = best_evidence.get("embedding_score", 0.0)
    keyword_score = best_evidence.get("keyword_score", 0.0)
    evidence_text = best_evidence.get("text", "")

    if has_scope_mismatch(claim, evidence_text):
        return True, "Claim contains scope-specific terms not covered by the evidence."

    if has_unsupported_absolute_claim(claim, evidence_text):
        return True, "Claim makes an absolute claim not supported by the evidence."

    if final_score < MIN_FINAL_SCORE_FOR_VERIFICATION:
        return True, "Top evidence final score is too low."

    if embedding_score < MIN_EMBEDDING_SCORE_FOR_VERIFICATION:
        return True, "Top evidence embedding similarity is too low."

    if keyword_score < MIN_KEYWORD_SCORE_FOR_VERIFICATION:
        return True, "Top evidence keyword overlap is too low."

    return False, ""


def verify_claim(
    claim: str,
    evidence_db: List[Dict[str, str]],
    verification_rules: List[Dict],
    model: SentenceTransformer,
    evidence_embeddings: np.ndarray
) -> Dict:
    """Verify a claim against multiple retrieved evidence candidates.

    Retrieved evidence is evaluated in ranked order. A high-ranking
    evidence item that does not match a verification rule no longer blocks
    a lower-ranking item that can support or refute the claim.
    """

    evidence_results = search_evidence(
        claim=claim,
        evidence_list=evidence_db,
        model=model,
        evidence_embeddings=evidence_embeddings
    )

    if not evidence_results:
        return {
            "claim": claim,
            "label": "Uncertain",
            "confidence": 0.3,
            "evidence": [],
            "matched_rule": None,
            "abstention_reason": "No relevant evidence found."
        }

    verification_candidates = []
    abstention_reasons = []
    eligible_evidence_count = 0

    for evidence in evidence_results:
        abstain, reason = should_abstain(
            evidence,
            claim
        )

        if abstain:
            if reason and reason not in abstention_reasons:
                abstention_reasons.append(reason)

            continue

        eligible_evidence_count += 1

        label, confidence, matched_rule = (
            infer_label_from_claim_and_evidence(
                claim=claim,
                evidence_text=evidence.get("text", "")
            )
        )

        if label == "Uncertain":
            continue

        verification_candidates.append(
            {
                "label": label,
                "confidence": confidence,
                "matched_rule": matched_rule,
                "retrieval_score": evidence.get(
                    "score",
                    0.0
                ),
                "evidence": evidence
            }
        )

    if verification_candidates:
        candidate_labels = {
            candidate["label"]
            for candidate in verification_candidates
        }

        if len(candidate_labels) > 1:
            return {
                "claim": claim,
                "label": "Uncertain",
                "confidence": 0.45,
                "evidence": evidence_results,
                "matched_rule": None,
                "abstention_reason": (
                    "Retrieved evidence produced conflicting "
                    "rule-based labels."
                )
            }

        selected_candidate = max(
            verification_candidates,
            key=lambda candidate: (
                candidate["retrieval_score"],
                candidate["confidence"]
            )
        )

        return {
            "claim": claim,
            "label": selected_candidate["label"],
            "confidence": selected_candidate["confidence"],
            "evidence": evidence_results,
            "matched_rule": selected_candidate["matched_rule"],
            "abstention_reason": None
        }

    if eligible_evidence_count == 0:
        if abstention_reasons:
            abstention_reason = (
                "All retrieved evidence candidates were rejected: "
                + " | ".join(abstention_reasons)
            )
        else:
            abstention_reason = (
                "All retrieved evidence candidates failed "
                "verification thresholds."
            )

        confidence = 0.35

    else:
        abstention_reason = (
            "Relevant evidence was retrieved, but no "
            "verification rule matched."
        )
        confidence = 0.5

    return {
        "claim": claim,
        "label": "Uncertain",
        "confidence": confidence,
        "evidence": evidence_results,
        "matched_rule": None,
        "abstention_reason": abstention_reason
    }

def build_success_response(result: Dict) -> Dict:
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": {
            "claim": result["claim"],
            "prediction": {
                "label": result["label"],
                "confidence": result["confidence"]
            },
            "evidence": result["evidence"]
        },
        "metadata": {
            "retrieval_method": "embedding_plus_lightweight_reranking",
            "embedding_model": MODEL_NAME,
            "evidence_count": len(result["evidence"]),
            "matched_rule": result.get("matched_rule"),
            "abstention_reason": result.get("abstention_reason"),
            "min_final_score_for_verification": MIN_FINAL_SCORE_FOR_VERIFICATION,
            "min_embedding_score_for_verification": MIN_EMBEDDING_SCORE_FOR_VERIFICATION,
            "min_keyword_score_for_verification": MIN_KEYWORD_SCORE_FOR_VERIFICATION
        }
    }


def build_error_response(message: str) -> Dict:
    return {
        "status": "error",
        "timestamp": datetime.now().isoformat(),
        "error": {
            "message": message
        }
    }


def save_log(response: Dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)

    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(response, ensure_ascii=False) + "\n")


def print_response(response: Dict) -> None:
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        evidence_db = load_evidence(DATA_PATH)
        verification_rules = load_rules(RULES_PATH)

        print(f"Loading embedding model: {MODEL_NAME}")
        model = SentenceTransformer(MODEL_NAME)

        evidence_embeddings = get_or_build_evidence_embeddings(evidence_db, model)

        print("System ready.")
        print("-" * 50)

    except Exception as error:
        response = build_error_response(str(error))
        print_response(response)
        save_log(response)
        raise SystemExit

    while True:
        claim = input("Enter a claim, or type 'q' to quit: ")

        if claim.lower() in ["q", "quit", "exit"]:
            print("Goodbye.")
            break

        is_valid, error_message = validate_claim(claim)

        if not is_valid:
            response = build_error_response(error_message)
            print_response(response)
            save_log(response)
            print("-" * 50)
            continue

        try:
            result = verify_claim(
                claim=claim,
                evidence_db=evidence_db,
                verification_rules=verification_rules,
                model=model,
                evidence_embeddings=evidence_embeddings
            )

            response = build_success_response(result)

        except Exception as error:
            response = build_error_response(str(error))

        save_log(response)
        print_response(response)
        print("-" * 50)