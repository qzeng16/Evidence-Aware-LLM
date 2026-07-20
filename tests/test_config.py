"""Tests for application configuration."""

import pytest

from app.config import (
    DEFAULT_VERIFIER_MODE,
    HYBRID_MODE,
    LLM_ONLY_MODE,
    RULE_ONLY_MODE,
    AppConfig,
    ConfigurationError,
    load_app_config,
    normalize_verifier_mode,
)


def test_missing_verifier_mode_uses_rule_only():
    """Missing configuration should preserve current behavior."""

    config = load_app_config({})

    assert config.verifier_mode == DEFAULT_VERIFIER_MODE
    assert config.verifier_mode == RULE_ONLY_MODE
    assert config.uses_rule_verifier is True
    assert config.uses_llm_verifier is False


def test_empty_verifier_mode_uses_rule_only():
    """Blank environment values should use the safe default."""

    config = load_app_config(
        {
            "VERIFIER_MODE": "   ",
        }
    )

    assert config.verifier_mode == RULE_ONLY_MODE


@pytest.mark.parametrize(
    "configured_value, expected_mode",
    [
        ("rule_only", RULE_ONLY_MODE),
        ("RULE_ONLY", RULE_ONLY_MODE),
        (" llm_only ", LLM_ONLY_MODE),
        ("HYBRID", HYBRID_MODE),
    ],
)
def test_supported_verifier_modes_are_normalized(
    configured_value,
    expected_mode,
):
    """Supported modes should be normalized to lowercase."""

    config = load_app_config(
        {
            "VERIFIER_MODE": configured_value,
        }
    )

    assert config.verifier_mode == expected_mode


def test_hybrid_mode_uses_both_verifiers():
    """Hybrid mode should enable rule and LLM verification."""

    config = AppConfig(
        verifier_mode=HYBRID_MODE,
    )

    assert config.uses_rule_verifier is True
    assert config.uses_llm_verifier is True


def test_llm_only_mode_disables_rule_verifier():
    """LLM-only mode should not run the rule verifier."""

    config = AppConfig(
        verifier_mode=LLM_ONLY_MODE,
    )

    assert config.uses_rule_verifier is False
    assert config.uses_llm_verifier is True


def test_invalid_verifier_mode_is_rejected():
    """Unsupported values should fail instead of silently falling back."""

    with pytest.raises(
        ConfigurationError,
        match="Unsupported verifier mode",
    ):
        normalize_verifier_mode("hybird")
