"""Application service initialization and claim verification."""

from typing import Any, Dict, Optional

from sentence_transformers import SentenceTransformer

from app.config import (
    DEFAULT_VERIFIER_MODE,
    HYBRID_MODE,
    LLM_ONLY_MODE,
    RULE_ONLY_MODE,
    AppConfig,
    load_app_config,
)
from app.llm_clients import (
    OPENAI_PROVIDER,
    OpenAIResponsesClient,
)
from app.verifiers import (
    HybridVerifier,
    LLMVerifier,
    RuleVerifier,
    Verifier,
)
import layer0_verifier as verifier


system_state: Dict[str, Any] = {
    "evidence_db": None,
    "verification_rules": None,
    "model": None,
    "evidence_embeddings": None,
    "config": None,
    "active_verifier": None,
    "initialization_error": None,
}


def reset_service_state() -> None:
    """Reset all in-memory service resources."""

    system_state["evidence_db"] = None
    system_state["verification_rules"] = None
    system_state["model"] = None
    system_state["evidence_embeddings"] = None
    system_state["config"] = None
    system_state["active_verifier"] = None
    system_state["initialization_error"] = None


def get_app_config() -> Optional[AppConfig]:
    """Return the currently loaded application configuration."""

    config = system_state.get("config")

    if isinstance(config, AppConfig):
        return config

    return None


def get_active_verifier() -> Optional[Verifier]:
    """Return the initialized verifier backend."""

    active_verifier = system_state.get(
        "active_verifier"
    )

    if active_verifier is None:
        return None

    return active_verifier


def get_configured_verifier_mode() -> str:
    """Return the configured verifier mode."""

    config = get_app_config()

    if config is None:
        return DEFAULT_VERIFIER_MODE

    return config.verifier_mode


def is_llm_verifier_available() -> bool:
    """Return whether an LLM backend is currently active."""

    active_verifier = get_active_verifier()

    if active_verifier is None:
        return False

    return active_verifier.verifier_type.value in {
        "llm",
        "hybrid",
    }


def is_openai_api_key_configured() -> bool:
    """Return whether an OpenAI key exists without exposing it."""

    config = get_app_config()

    return bool(
        config is not None
        and config.has_openai_api_key
    )


def get_llm_provider_name() -> Optional[str]:
    """Return the configured LLM provider name."""

    config = get_app_config()

    if (
        config is None
        or not config.uses_llm_verifier
    ):
        return None

    return OPENAI_PROVIDER


def get_llm_model_name() -> Optional[str]:
    """Return the configured LLM model name."""

    config = get_app_config()

    if (
        config is None
        or not config.uses_llm_verifier
    ):
        return None

    return config.openai_model

def is_service_ready() -> bool:
    """Return whether the configured verifier can process requests."""

    config = get_app_config()
    active_verifier = get_active_verifier()

    if config is None:
        return False

    if active_verifier is None:
        return False

    if (
        system_state.get("initialization_error")
        is not None
    ):
        return False

    required_resource_names = [
        "evidence_db",
        "model",
        "evidence_embeddings",
    ]

    if config.uses_rule_verifier:
        required_resource_names.append(
            "verification_rules"
        )

    return all(
        system_state.get(resource_name) is not None
        for resource_name in required_resource_names
    )

def get_active_verifier_mode() -> Optional[str]:
    """Return the verifier backend currently handling requests."""

    active_verifier = get_active_verifier()

    if active_verifier is None:
        return None

    return active_verifier.verifier_type.value


def get_service_status() -> Dict[str, Any]:
    """Return safe readiness and verifier metadata."""

    return {
        "status": (
            "ready"
            if is_service_ready()
            else "loading_or_unavailable"
        ),
        "verifier_mode": get_configured_verifier_mode(),
        "active_verifier_mode": (
            get_active_verifier_mode()
        ),
        "llm_verifier_available": (
            is_llm_verifier_available()
        ),
        "llm_provider": get_llm_provider_name(),
        "llm_model": get_llm_model_name(),
        "openai_api_key_configured": (
            is_openai_api_key_configured()
        ),
        "initialization_error": system_state.get(
            "initialization_error"
        ),
    }

def initialize_service() -> None:
    """Load resources and initialize the configured verifier."""

    reset_service_state()

    config = load_app_config()
    system_state["config"] = config

    print(
        "Configured verifier mode: "
        f"{config.verifier_mode}"
    )

    if (
        config.uses_llm_verifier
        and not config.has_openai_api_key
    ):
        error_message = (
            "OPENAI_API_KEY is required when "
            "the configured verifier mode uses "
            "an LLM backend."
        )

        system_state[
            "initialization_error"
        ] = error_message

        print(
            "Service initialization paused: "
            f"{error_message}"
        )

        return

    print("Loading evidence database...")

    evidence_db = verifier.load_evidence(
        verifier.DATA_PATH
    )

    verification_rules = None

    if config.uses_rule_verifier:
        print("Loading verification rules...")

        verification_rules = verifier.load_rules(
            verifier.RULES_PATH
        )

    print(
        "Loading embedding model: "
        f"{verifier.MODEL_NAME}"
    )

    model = SentenceTransformer(
        verifier.MODEL_NAME
    )

    print(
        "Loading or building evidence embeddings..."
    )

    evidence_embeddings = (
        verifier.get_or_build_evidence_embeddings(
            evidence_db,
            model,
        )
    )

    rule_verifier = None
    llm_verifier = None

    if config.uses_rule_verifier:
        rule_verifier = RuleVerifier(
            evidence_db=evidence_db,
            verification_rules=(
                verification_rules
            ),
            model=model,
            evidence_embeddings=(
                evidence_embeddings
            ),
        )

    if config.uses_llm_verifier:
        llm_client = OpenAIResponsesClient(
            api_key=(
                config.openai_api_key
                or ""
            ),
            model=config.openai_model,
            timeout_seconds=(
                config.openai_timeout_seconds
            ),
            max_retries=(
                config.openai_max_retries
            ),
        )

        llm_verifier = LLMVerifier(
            evidence_db=evidence_db,
            model=model,
            evidence_embeddings=(
                evidence_embeddings
            ),
            client=llm_client,
        )

    if config.verifier_mode == RULE_ONLY_MODE:
        if rule_verifier is None:
            raise RuntimeError(
                "RuleVerifier was not initialized."
            )

        active_verifier = rule_verifier

    elif config.verifier_mode == LLM_ONLY_MODE:
        if llm_verifier is None:
            raise RuntimeError(
                "LLMVerifier was not initialized."
            )

        active_verifier = llm_verifier

    elif config.verifier_mode == HYBRID_MODE:
        if (
            rule_verifier is None
            or llm_verifier is None
        ):
            raise RuntimeError(
                "Hybrid mode requires both rule "
                "and LLM verifiers."
            )

        active_verifier = HybridVerifier(
            rule_verifier=rule_verifier,
            llm_verifier=llm_verifier,
        )

    else:
        raise RuntimeError(
            "No verifier implementation is "
            "available for mode "
            f"'{config.verifier_mode}'."
        )

    system_state["evidence_db"] = evidence_db
    system_state[
        "verification_rules"
    ] = verification_rules
    system_state["model"] = model
    system_state[
        "evidence_embeddings"
    ] = evidence_embeddings
    system_state[
        "active_verifier"
    ] = active_verifier

    print(
        "API system ready with active verifier: "
        f"{active_verifier.verifier_type.value}"
    )

def attach_execution_metadata(
    response: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach safe execution metadata to an API response."""

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
            "llm_verifier_available": (
                is_llm_verifier_available()
            ),
            "llm_provider": (
                get_llm_provider_name()
            ),
            "llm_model": (
                get_llm_model_name()
            ),
            "openai_api_key_configured": (
                is_openai_api_key_configured()
            ),
        }
    )

    response["metadata"] = metadata

    return response

def verify_claim_service(
    claim: str,
) -> Dict[str, Any]:
    """Validate and verify a claim through the active backend."""

    if not is_service_ready():
        error_message = (
            system_state.get(
                "initialization_error"
            )
            or "Service is not ready."
        )

        response = verifier.build_error_response(
            error_message
        )
        response = attach_execution_metadata(
            response
        )
        verifier.save_log(response)

        return response

    is_valid, error_message = (
        verifier.validate_claim(claim)
    )

    if not is_valid:
        response = verifier.build_error_response(
            error_message
        )
        response = attach_execution_metadata(
            response
        )
        verifier.save_log(response)

        return response

    try:
        active_verifier = get_active_verifier()

        if active_verifier is None:
            raise RuntimeError(
                "No active verifier is available."
            )

        verification_run = (
            active_verifier.verify(claim)
        )

        legacy_result = (
            verification_run.to_legacy_dict()
        )

        response = verifier.build_success_response(
            legacy_result
        )

        response["data"]["verification"] = (
            verification_run.result.to_dict()
        )

    except Exception as error:
        response = verifier.build_error_response(
            str(error)
        )

    response = attach_execution_metadata(
        response
    )
    verifier.save_log(response)

    return response
