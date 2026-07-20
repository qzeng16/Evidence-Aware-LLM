"""Tests for OpenAI-backed LLM service initialization."""

from typing import Any, Dict, Optional

import numpy as np
import pytest

from app.config import (
    LLM_ONLY_MODE,
    AppConfig,
)
from app.verification_result import (
    VerificationResult,
    VerifierType,
)
from app.verifiers.base import VerificationRun
import app.services as services


class FakeSentenceTransformer:
    """Small replacement for the embedding model."""

    def __init__(self, model_name: str):
        self.model_name = model_name


class FakeOpenAIClient:
    """Record OpenAI provider configuration."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries


class FakeInitializedLLMVerifier:
    """Record dependencies supplied during initialization."""

    verifier_type = VerifierType.LLM

    def __init__(
        self,
        evidence_db,
        model,
        evidence_embeddings,
        client,
    ) -> None:
        self.evidence_db = evidence_db
        self.model = model
        self.evidence_embeddings = (
            evidence_embeddings
        )
        self.client = client

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        raise AssertionError(
            "Initialization test should not call verify()."
        )


@pytest.fixture(autouse=True)
def reset_service_state():
    """Prevent state leakage between tests."""

    services.reset_service_state()

    yield

    services.reset_service_state()


def configure_fake_llm_resources(
    monkeypatch: pytest.MonkeyPatch,
    config: AppConfig,
) -> None:
    """Patch heavy and external initialization dependencies."""

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: config,
    )

    monkeypatch.setattr(
        services,
        "SentenceTransformer",
        FakeSentenceTransformer,
    )

    monkeypatch.setattr(
        services.verifier,
        "load_evidence",
        lambda file_path: [
            {
                "evidence_id": "test-001",
                "title": "Test Evidence",
                "text": (
                    "Evidence used for LLM service "
                    "initialization testing."
                ),
            }
        ],
    )

    def fail_if_rules_are_loaded(file_path):
        del file_path

        raise AssertionError(
            "llm_only should not load rule definitions."
        )

    monkeypatch.setattr(
        services.verifier,
        "load_rules",
        fail_if_rules_are_loaded,
    )

    monkeypatch.setattr(
        services.verifier,
        "get_or_build_evidence_embeddings",
        lambda evidence_db, model: np.zeros(
            (1, 3),
            dtype=np.float32,
        ),
    )

    monkeypatch.setattr(
        services,
        "OpenAIResponsesClient",
        FakeOpenAIClient,
    )

    monkeypatch.setattr(
        services,
        "LLMVerifier",
        FakeInitializedLLMVerifier,
    )


def test_llm_only_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
):
    """Missing credentials should stop before heavy initialization."""

    config = AppConfig(
        verifier_mode=LLM_ONLY_MODE,
        openai_api_key=None,
    )

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: config,
    )

    model_was_loaded = False

    def fail_if_model_is_loaded(model_name):
        nonlocal model_was_loaded

        model_was_loaded = True

        raise AssertionError(
            "Embedding model should not load without an API key."
        )

    monkeypatch.setattr(
        services,
        "SentenceTransformer",
        fail_if_model_is_loaded,
    )

    services.initialize_service()

    status = services.get_service_status()

    assert services.is_service_ready() is False
    assert status["verifier_mode"] == LLM_ONLY_MODE
    assert status["active_verifier_mode"] is None
    assert status["llm_verifier_available"] is False
    assert "OPENAI_API_KEY" in (
        status["initialization_error"]
    )
    assert model_was_loaded is False


def test_llm_only_initializes_openai_verifier(
    monkeypatch: pytest.MonkeyPatch,
):
    """Valid provider configuration should create LLMVerifier."""

    config = AppConfig(
        verifier_mode=LLM_ONLY_MODE,
        openai_api_key="test-secret-key",
        openai_model="test-openai-model",
        openai_timeout_seconds=14.5,
        openai_max_retries=4,
    )

    configure_fake_llm_resources(
        monkeypatch,
        config,
    )

    services.initialize_service()

    status = services.get_service_status()
    active_verifier = (
        services.get_active_verifier()
    )

    assert services.is_service_ready() is True
    assert status["status"] == "ready"
    assert status["verifier_mode"] == LLM_ONLY_MODE
    assert status["active_verifier_mode"] == "llm"
    assert status["llm_verifier_available"] is True
    assert status["initialization_error"] is None

    assert isinstance(
        active_verifier,
        FakeInitializedLLMVerifier,
    )

    assert (
        services.system_state[
            "verification_rules"
        ]
        is None
    )

    client = active_verifier.client

    assert isinstance(
        client,
        FakeOpenAIClient,
    )
    assert client.api_key == "test-secret-key"
    assert client.model == "test-openai-model"
    assert client.timeout_seconds == 14.5
    assert client.max_retries == 4


class FakeActiveLLMVerifier:
    """Return one deterministic unified LLM result."""

    verifier_type = VerifierType.LLM

    def __init__(
        self,
        run: VerificationRun,
    ) -> None:
        self.run = run
        self.received_claim: Optional[str] = None

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        self.received_claim = claim

        return self.run


def test_llm_service_response_uses_unified_interface(
    monkeypatch: pytest.MonkeyPatch,
):
    """The existing service workflow should handle an LLM backend."""

    claim = (
        "Retrieval augmented generation can "
        "improve factual reliability."
    )

    result = VerificationResult(
        label="Supported",
        confidence=0.84,
        reason=(
            "Evidence test-001 directly supports "
            "the claim."
        ),
        verifier_type="llm",
        matched_evidence_ids=(
            "test-001",
        ),
    )

    run = VerificationRun(
        claim=claim,
        result=result,
        evidence=(
            {
                "evidence_id": "test-001",
                "title": "Test Evidence",
                "text": (
                    "RAG can improve factual reliability."
                ),
            },
        ),
    )

    active_verifier = FakeActiveLLMVerifier(
        run
    )

    services.system_state.update(
        {
            "evidence_db": [],
            "verification_rules": None,
            "model": object(),
            "evidence_embeddings": object(),
            "config": AppConfig(
                verifier_mode=LLM_ONLY_MODE,
                openai_api_key="test-key",
            ),
            "active_verifier": active_verifier,
            "initialization_error": None,
        }
    )

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda value: (
            True,
            "",
        ),
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    response = services.verify_claim_service(
        claim
    )

    assert response["status"] == "success"
    assert active_verifier.received_claim == claim

    assert response["data"][
        "prediction"
    ] == {
        "label": "Supported",
        "confidence": 0.84,
    }

    assert response["data"][
        "verification"
    ]["verifier_type"] == "llm"

    assert response["data"][
        "verification"
    ]["matched_evidence_ids"] == [
        "test-001",
    ]

    assert response["metadata"][
        "verifier_mode"
    ] == LLM_ONLY_MODE

    assert response["metadata"][
        "active_verifier_mode"
    ] == "llm"

    assert response["metadata"][
        "llm_verifier_available"
    ] is True
