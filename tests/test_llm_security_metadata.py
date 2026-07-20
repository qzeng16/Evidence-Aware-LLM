"""Tests preventing OpenAI credentials from entering responses or logs."""

import json
from typing import Optional

import pytest

from app.config import (
    LLM_ONLY_MODE,
    RULE_ONLY_MODE,
    AppConfig,
)
from app.llm_clients import (
    PROVIDER_REQUEST_ERROR,
    LLMClientError,
)
from app.verification_result import (
    VerifierType,
)
import app.services as services


class FakeLLMVerifier:
    """LLM backend that raises a safe provider error."""

    verifier_type = VerifierType.LLM

    def __init__(self) -> None:
        self.received_claim: Optional[str] = None

    def verify(self, claim: str):
        self.received_claim = claim

        raise LLMClientError(
            "OpenAI provider request failed.",
            error_code=PROVIDER_REQUEST_ERROR,
            retryable=True,
        )


class FakeRuleVerifier:
    """Minimal rule backend for status tests."""

    verifier_type = VerifierType.RULE


@pytest.fixture(autouse=True)
def reset_service_state():
    """Prevent service state from leaking between tests."""

    services.reset_service_state()

    yield

    services.reset_service_state()


def prepare_llm_state(
    secret_key: str,
) -> FakeLLMVerifier:
    """Populate a ready LLM service state."""

    active_verifier = FakeLLMVerifier()

    services.system_state.update(
        {
            "evidence_db": [],
            "verification_rules": None,
            "model": object(),
            "evidence_embeddings": object(),
            "config": AppConfig(
                verifier_mode=LLM_ONLY_MODE,
                openai_api_key=secret_key,
                openai_model="test-openai-model",
            ),
            "active_verifier": active_verifier,
            "initialization_error": None,
        }
    )

    return active_verifier


def test_health_exposes_safe_provider_metadata():
    """Health should report provider state without credentials."""

    secret_key = "secret-key-that-must-not-appear"

    prepare_llm_state(secret_key)

    status = services.get_service_status()
    serialized_status = json.dumps(status)

    assert status["status"] == "ready"
    assert status["llm_verifier_available"] is True
    assert status["llm_provider"] == "openai"
    assert status["llm_model"] == (
        "test-openai-model"
    )
    assert (
        status["openai_api_key_configured"]
        is True
    )

    assert secret_key not in serialized_status
    assert "openai_api_key" not in status
    assert "OPENAI_API_KEY" not in serialized_status


def test_error_response_and_log_do_not_expose_key(
    monkeypatch: pytest.MonkeyPatch,
):
    """Provider failures should be logged without credentials."""

    secret_key = "secret-key-that-must-not-appear"

    active_verifier = prepare_llm_state(
        secret_key
    )

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda claim: (
            True,
            "",
        ),
    )

    logged_responses = []

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: logged_responses.append(
            response
        ),
    )

    claim = "A valid claim for a provider error test."

    response = services.verify_claim_service(
        claim
    )

    assert response["status"] == "error"
    assert active_verifier.received_claim == claim
    assert len(logged_responses) == 1

    serialized_response = json.dumps(response)
    serialized_log = json.dumps(
        logged_responses[0]
    )

    assert secret_key not in serialized_response
    assert secret_key not in serialized_log
    assert "OPENAI_API_KEY" not in serialized_response
    assert "OPENAI_API_KEY" not in serialized_log

    assert response["metadata"][
        "llm_provider"
    ] == "openai"

    assert response["metadata"][
        "llm_model"
    ] == "test-openai-model"

    assert response["metadata"][
        "openai_api_key_configured"
    ] is True


def test_rule_mode_does_not_report_active_llm():
    """Rule-only mode should not claim an active LLM backend."""

    services.system_state.update(
        {
            "evidence_db": [],
            "verification_rules": [],
            "model": object(),
            "evidence_embeddings": object(),
            "config": AppConfig(
                verifier_mode=RULE_ONLY_MODE,
                openai_api_key=None,
            ),
            "active_verifier": FakeRuleVerifier(),
            "initialization_error": None,
        }
    )

    status = services.get_service_status()

    assert status["status"] == "ready"
    assert status["llm_verifier_available"] is False
    assert status["llm_provider"] is None
    assert status["llm_model"] is None
    assert (
        status["openai_api_key_configured"]
        is False
    )
