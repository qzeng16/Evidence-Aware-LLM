"""Tests for verifier-mode service integration."""

from typing import Any, Dict

import numpy as np
import pytest

from app.config import (
    HYBRID_MODE,
    RULE_ONLY_MODE,
    AppConfig,
)
from app.verification_result import VerifierType
import app.services as services


@pytest.fixture(autouse=True)
def reset_state_between_tests():
    """Ensure service state does not leak between tests."""

    services.reset_service_state()

    yield

    services.reset_service_state()


class FakeSentenceTransformer:
    """Small stand-in for the real embedding model."""

    def __init__(self, model_name: str):
        self.model_name = model_name


def configure_fake_rule_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch external resources used during initialization."""

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: AppConfig(
            verifier_mode=RULE_ONLY_MODE
        ),
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
                "title": "Test Evidence",
                "text": (
                    "This evidence is used for service "
                    "configuration testing."
                ),
            }
        ],
    )

    monkeypatch.setattr(
        services.verifier,
        "load_rules",
        lambda file_path: [],
    )

    monkeypatch.setattr(
        services.verifier,
        "get_or_build_evidence_embeddings",
        lambda evidence_db, model: np.zeros(
            (1, 3),
            dtype=np.float32,
        ),
    )


def test_rule_only_service_initializes(
    monkeypatch: pytest.MonkeyPatch,
):
    """The default implemented mode should become ready."""

    configure_fake_rule_service(monkeypatch)

    services.initialize_service()

    status = services.get_service_status()

    assert services.is_service_ready() is True
    assert status["status"] == "ready"
    assert status["verifier_mode"] == RULE_ONLY_MODE
    assert (
        status["active_verifier_mode"]
        == VerifierType.RULE.value
    )
    assert status["llm_verifier_available"] is False
    assert status["initialization_error"] is None


def test_unimplemented_hybrid_mode_is_not_silent(
    monkeypatch: pytest.MonkeyPatch,
):
    """Hybrid mode should not silently execute rule-only."""

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: AppConfig(
            verifier_mode=HYBRID_MODE
        ),
    )

    services.initialize_service()

    status = services.get_service_status()

    assert services.is_service_ready() is False
    assert status["status"] == (
        "loading_or_unavailable"
    )
    assert status["verifier_mode"] == HYBRID_MODE
    assert status["active_verifier_mode"] is None
    assert status["llm_verifier_available"] is False
    assert "not been connected" in (
        status["initialization_error"]
    )


def test_verify_response_contains_mode_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    """Successful responses should identify the active verifier."""

    configure_fake_rule_service(monkeypatch)
    services.initialize_service()

    verification_result: Dict[str, Any] = {
        "claim": "This is a valid test claim.",
        "label": "Supported",
        "confidence": 0.86,
        "evidence": [],
        "matched_rule": "test-rule",
        "abstention_reason": None,
    }

    monkeypatch.setattr(
        services.verifier,
        "verify_claim",
        lambda **kwargs: verification_result,
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    response = services.verify_claim_service(
        "This is a valid test claim."
    )

    assert response["status"] == "success"
    assert (
        response["metadata"]["verifier_mode"]
        == RULE_ONLY_MODE
    )
    assert (
        response["metadata"]["active_verifier_mode"]
        == VerifierType.RULE.value
    )
    assert (
        response["metadata"][
            "llm_verifier_available"
        ]
        is False
    )


def test_unready_response_contains_configuration_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    """Unavailable-mode errors should still expose configuration."""

    monkeypatch.setattr(
        services,
        "load_app_config",
        lambda: AppConfig(
            verifier_mode=HYBRID_MODE
        ),
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    services.initialize_service()

    response = services.verify_claim_service(
        "This is a valid test claim."
    )

    assert response["status"] == "error"
    assert (
        response["metadata"]["verifier_mode"]
        == HYBRID_MODE
    )
    assert (
        response["metadata"]["active_verifier_mode"]
        is None
    )
