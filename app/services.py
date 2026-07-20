"""Application service initialization and claim verification."""

from typing import Any, Dict, Optional

from sentence_transformers import SentenceTransformer

from app.config import (
    DEFAULT_VERIFIER_MODE,
    RULE_ONLY_MODE,
    AppConfig,
    load_app_config,
)
import layer0_verifier as verifier


system_state: Dict[str, Any] = {
    "evidence_db": None,
    "verification_rules": None,
    "model": None,
    "evidence_embeddings": None,
    "config": None,
    "initialization_error": None,
}


def reset_service_state() -> None:
    """Reset all in-memory service resources.

    This function is primarily useful for isolated tests and controlled
    service reinitialization.
    """

    system_state["evidence_db"] = None
    system_state["verification_rules"] = None
    system_state["model"] = None
    system_state["evidence_embeddings"] = None
    system_state["config"] = None
    system_state["initialization_error"] = None


def get_app_config() -> Optional[AppConfig]:
    """Return the currently loaded application configuration."""

    config = system_state.get("config")

    if isinstance(config, AppConfig):
        return config

    return None


def get_configured_verifier_mode() -> str:
    """Return the configured verifier mode."""

    config = get_app_config()

    if config is None:
        return DEFAULT_VERIFIER_MODE

    return config.verifier_mode


def is_service_ready() -> bool:
    """Return whether all rule-verifier resources are initialized."""

    required_resources = [
        system_state.get("evidence_db"),
        system_state.get("verification_rules"),
        system_state.get("model"),
        system_state.get("evidence_embeddings"),
        system_state.get("config"),
    ]

    return (
        system_state.get("initialization_error") is None
        and all(
            resource is not None
            for resource in required_resources
        )
    )


def get_active_verifier_mode() -> Optional[str]:
    """Return the verifier mode currently executing requests."""

    if not is_service_ready():
        return None

    return RULE_ONLY_MODE


def get_service_status() -> Dict[str, Any]:
    """Return readiness and verifier-mode information."""

    return {
        "status": (
            "ready"
            if is_service_ready()
            else "loading_or_unavailable"
        ),
        "verifier_mode": get_configured_verifier_mode(),
        "active_verifier_mode": get_active_verifier_mode(),
        "llm_verifier_available": False,
        "initialization_error": system_state.get(
            "initialization_error"
        ),
    }


def initialize_service() -> None:
    """Load configuration and initialize verification resources."""

    reset_service_state()

    config = load_app_config()
    system_state["config"] = config

    print(
        "Configured verifier mode: "
        f"{config.verifier_mode}"
    )

    if config.verifier_mode != RULE_ONLY_MODE:
        error_message = (
            f"Verifier mode '{config.verifier_mode}' is configured, "
            "but the LLM verifier has not been connected yet. "
            "Use VERIFIER_MODE=rule_only until the LLM verifier "
            "implementation is available."
        )

        system_state["initialization_error"] = error_message
        print(f"Service initialization paused: {error_message}")
        return

    print("Loading evidence database...")
    evidence_db = verifier.load_evidence(
        verifier.DATA_PATH
    )

    print("Loading verification rules...")
    verification_rules = verifier.load_rules(
        verifier.RULES_PATH
    )

    print(
        f"Loading embedding model: "
        f"{verifier.MODEL_NAME}"
    )
    model = SentenceTransformer(
        verifier.MODEL_NAME
    )

    print("Loading or building evidence embeddings...")
    evidence_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            evidence_db,
            model,
        )
    )

    system_state["evidence_db"] = evidence_db
    system_state["verification_rules"] = verification_rules
    system_state["model"] = model
    system_state["evidence_embeddings"] = (
        evidence_embeddings
    )

    print("API system ready in rule_only mode.")


def attach_execution_metadata(
    response: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach verifier execution details to an API response."""

    metadata = response.get("metadata")

    if not isinstance(metadata, dict):
        metadata = {}

    metadata.update(
        {
            "verifier_mode": (
                get_configured_verifier_mode()
            ),
            "active_verifier_mode": (
                get_active_verifier_mode()
            ),
            "llm_verifier_available": False,
        }
    )

    response["metadata"] = metadata

    return response


def verify_claim_service(
    claim: str,
) -> Dict[str, Any]:
    """Validate and verify a claim using the active verifier."""

    if not is_service_ready():
        error_message = (
            system_state.get("initialization_error")
            or "Service is not ready."
        )

        response = verifier.build_error_response(
            error_message
        )
        response = attach_execution_metadata(response)
        verifier.save_log(response)

        return response

    is_valid, error_message = verifier.validate_claim(
        claim
    )

    if not is_valid:
        response = verifier.build_error_response(
            error_message
        )
        response = attach_execution_metadata(response)
        verifier.save_log(response)

        return response

    try:
        result = verifier.verify_claim(
            claim=claim,
            evidence_db=system_state["evidence_db"],
            verification_rules=system_state[
                "verification_rules"
            ],
            model=system_state["model"],
            evidence_embeddings=system_state[
                "evidence_embeddings"
            ],
        )

        response = verifier.build_success_response(
            result
        )

    except Exception as error:
        response = verifier.build_error_response(
            str(error)
        )

    response = attach_execution_metadata(response)
    verifier.save_log(response)

    return response
