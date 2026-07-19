from typing import Dict, Any

from sentence_transformers import SentenceTransformer

import layer0_verifier as verifier


system_state = {
    "evidence_db": None,
    "verification_rules": None,
    "model": None,
    "evidence_embeddings": None
}


def initialize_service() -> None:
    print("Loading evidence database...")
    evidence_db = verifier.load_evidence(verifier.DATA_PATH)

    print("Loading verification rules...")
    verification_rules = verifier.load_rules(verifier.RULES_PATH)

    print(f"Loading embedding model: {verifier.MODEL_NAME}")
    model = SentenceTransformer(verifier.MODEL_NAME)

    print("Loading or building evidence embeddings...")
    evidence_embeddings = verifier.get_or_build_evidence_embeddings(
        evidence_db,
        model
    )

    system_state["evidence_db"] = evidence_db
    system_state["verification_rules"] = verification_rules
    system_state["model"] = model
    system_state["evidence_embeddings"] = evidence_embeddings

    print("API system ready.")


def is_service_ready() -> bool:
    return all(value is not None for value in system_state.values())


def verify_claim_service(claim: str) -> Dict[str, Any]:
    if not is_service_ready():
        response = verifier.build_error_response("Service is not ready.")
        verifier.save_log(response)
        return response

    is_valid, error_message = verifier.validate_claim(claim)

    if not is_valid:
        response = verifier.build_error_response(error_message)
        verifier.save_log(response)
        return response

    try:
        result = verifier.verify_claim(
            claim=claim,
            evidence_db=system_state["evidence_db"],
            verification_rules=system_state["verification_rules"],
            model=system_state["model"],
            evidence_embeddings=system_state["evidence_embeddings"]
        )

        response = verifier.build_success_response(result)

    except Exception as error:
        response = verifier.build_error_response(str(error))

    verifier.save_log(response)
    return response
