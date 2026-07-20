"""Tests for hybrid service initialization."""

import pytest

from app.config import (
    HYBRID_MODE,
    AppConfig,
)
from app.verification_result import (
    VerifierType,
)
import app.services as services


class FakeSentenceTransformer:
    """Small embedding model replacement."""

    def __init__(
        self,
        model_name: str,
    ) -> None:
        self.model_name = model_name


class FakeOpenAIClient:
    """Record provider configuration."""

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


class FakeRuleVerifier:
    """Record rule verifier initialization."""

    verifier_type = VerifierType.RULE

    def __init__(
        self,
        evidence_db,
        verification_rules,
        model,
        evidence_embeddings,
    ) -> None:
        self.evidence_db = evidence_db
        self.verification_rules = (
            verification_rules
        )
        self.model = model
        self.evidence_embeddings = (
            evidence_embeddings
        )


class FakeLLMVerifier:
    """Record LLM verifier initialization."""

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


class FakeHybridVerifier:
    """Record hybrid verifier initialization."""

    verifier_type = VerifierType.HYBRID

    def __init__(
        self,
        rule_verifier,
        llm_verifier,
    ) -> None:
        self.rule_verifier = rule_verifier
        self.llm_verifier = llm_verifier


@pytest.fixture(autouse=True)
def reset_service_state():
    """Prevent test state leakage."""

    services.reset_service_state()

    yield

    services.reset_service_state()


def patch_hybrid_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    config: AppConfig,
) -> None:
    """Patch all heavy and external resources."""

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
        lambda path: [
            {
                "evidence_id": "test-001",
                "title": "Test Evidence",
                "text": "Test evidence text.",
            }
        ],
    )

    monkeypatch.setattr(
        services.verifier,
        "load_rules",
        lambda path: [
            {
                "rule_id": "rule-001",
            }
        ],
    )

    monkeypatch.setattr(
        services.verifier,
        "get_or_build_evidence_embeddings",
        lambda evidence_db, model: [
            [
                0.0,
                0.0,
                0.0,
            ]
        ],
    )

    monkeypatch.setattr(
        services,
        "OpenAIResponsesClient",
        FakeOpenAIClient,
    )

    monkeypatch.setattr(
        services,
        "RuleVerifier",
        FakeRuleVerifier,
    )

    monkeypatch.setattr(
        services,
        "LLMVerifier",
        FakeLLMVerifier,
    )

    monkeypatch.setattr(
        services,
        "HybridVerifier",
        FakeHybridVerifier,
    )


def test_hybrid_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
):
    """Hybrid mode should reject missing LLM credentials."""

    config = AppConfig(
        verifier_mode=HYBRID_MODE,
        openai_api_key=None,
    )

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: config,
    )

    model_loaded = False

    def fail_if_model_loads(model_name):
        nonlocal model_loaded

        model_loaded = True

        raise AssertionError(
            "Model should not load without a key."
        )

    monkeypatch.setattr(
        services,
        "SentenceTransformer",
        fail_if_model_loads,
    )

    services.initialize_service()

    status = services.get_service_status()

    assert status["status"] == (
        "loading_or_unavailable"
    )
    assert status["verifier_mode"] == (
        HYBRID_MODE
    )
    assert status[
        "active_verifier_mode"
    ] is None
    assert "OPENAI_API_KEY" in status[
        "initialization_error"
    ]
    assert model_loaded is False


def test_hybrid_initializes_both_backends(
    monkeypatch: pytest.MonkeyPatch,
):
    """Hybrid mode should construct both child verifiers."""

    config = AppConfig(
        verifier_mode=HYBRID_MODE,
        openai_api_key="test-secret-key",
        openai_model="test-model",
        openai_timeout_seconds=20.0,
        openai_max_retries=1,
    )

    patch_hybrid_dependencies(
        monkeypatch,
        config,
    )

    services.initialize_service()

    status = services.get_service_status()
    active_verifier = (
        services.get_active_verifier()
    )

    assert status["status"] == "ready"
    assert status["verifier_mode"] == (
        HYBRID_MODE
    )
    assert status[
        "active_verifier_mode"
    ] == "hybrid"
    assert status[
        "llm_verifier_available"
    ] is True
    assert status["llm_provider"] == (
        "openai"
    )
    assert status["llm_model"] == (
        "test-model"
    )
    assert status[
        "openai_api_key_configured"
    ] is True
    assert status[
        "initialization_error"
    ] is None

    assert isinstance(
        active_verifier,
        FakeHybridVerifier,
    )

    assert isinstance(
        active_verifier.rule_verifier,
        FakeRuleVerifier,
    )

    assert isinstance(
        active_verifier.llm_verifier,
        FakeLLMVerifier,
    )

    assert (
        active_verifier.rule_verifier
        .verification_rules
        == [
            {
                "rule_id": "rule-001",
            }
        ]
    )

    client = (
        active_verifier
        .llm_verifier
        .client
    )

    assert isinstance(
        client,
        FakeOpenAIClient,
    )
    assert client.api_key == (
        "test-secret-key"
    )
    assert client.model == "test-model"
    assert client.timeout_seconds == 20.0
    assert client.max_retries == 1
