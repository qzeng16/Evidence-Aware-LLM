"""Tests for OpenAI provider configuration."""

import pytest

from app.config import (
    DEFAULT_OPENAI_MAX_RETRIES,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
    ConfigurationError,
    load_app_config,
)


def test_openai_configuration_uses_defaults():
    """Missing provider settings should use safe defaults."""

    config = load_app_config({})

    assert config.openai_api_key is None
    assert config.has_openai_api_key is False
    assert (
        config.openai_model
        == DEFAULT_OPENAI_MODEL
    )
    assert (
        config.openai_timeout_seconds
        == DEFAULT_OPENAI_TIMEOUT_SECONDS
    )
    assert (
        config.openai_max_retries
        == DEFAULT_OPENAI_MAX_RETRIES
    )


def test_openai_configuration_reads_environment():
    """Provider settings should be parsed from the environment."""

    config = load_app_config(
        {
            "OPENAI_API_KEY": " test-secret-key ",
            "OPENAI_MODEL": " gpt-5-mini ",
            "OPENAI_TIMEOUT_SECONDS": "45.5",
            "OPENAI_MAX_RETRIES": "4",
        }
    )

    assert (
        config.openai_api_key
        == "test-secret-key"
    )
    assert config.has_openai_api_key is True
    assert config.openai_model == "gpt-5-mini"
    assert config.openai_timeout_seconds == 45.5
    assert config.openai_max_retries == 4


def test_blank_api_key_becomes_none():
    """Blank key values should not count as configured."""

    config = load_app_config(
        {
            "OPENAI_API_KEY": "   ",
        }
    )

    assert config.openai_api_key is None
    assert config.has_openai_api_key is False


def test_blank_model_uses_default():
    """Blank model values should use the default model."""

    config = load_app_config(
        {
            "OPENAI_MODEL": "   ",
        }
    )

    assert (
        config.openai_model
        == DEFAULT_OPENAI_MODEL
    )


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-1",
        "not-a-number",
    ],
)
def test_invalid_timeout_is_rejected(value):
    """Timeout must be a positive number."""

    with pytest.raises(
        ConfigurationError,
        match="OPENAI_TIMEOUT_SECONDS",
    ):
        load_app_config(
            {
                "OPENAI_TIMEOUT_SECONDS": value,
            }
        )


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "1.5",
        "not-an-integer",
    ],
)
def test_invalid_retry_count_is_rejected(value):
    """Retry count must be a nonnegative integer."""

    with pytest.raises(
        ConfigurationError,
        match="OPENAI_MAX_RETRIES",
    ):
        load_app_config(
            {
                "OPENAI_MAX_RETRIES": value,
            }
        )


def test_api_key_is_hidden_from_config_repr():
    """Configuration repr should not expose API keys."""

    secret_value = "secret-that-must-not-appear"

    config = load_app_config(
        {
            "OPENAI_API_KEY": secret_value,
        }
    )

    assert secret_value not in repr(config)
