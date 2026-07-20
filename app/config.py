"""Application configuration.

This module defines the verifier execution modes used by the API.

The default mode remains ``rule_only`` so the existing application
continues to work without an external LLM provider or API key.
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional


VERIFIER_MODE_ENV = "VERIFIER_MODE"

RULE_ONLY_MODE = "rule_only"
LLM_ONLY_MODE = "llm_only"
HYBRID_MODE = "hybrid"

DEFAULT_VERIFIER_MODE = RULE_ONLY_MODE

SUPPORTED_VERIFIER_MODES = {
    RULE_ONLY_MODE,
    LLM_ONLY_MODE,
    HYBRID_MODE,
}


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Validated application configuration."""

    verifier_mode: str = DEFAULT_VERIFIER_MODE

    @property
    def uses_rule_verifier(self) -> bool:
        """Return whether the configured mode uses rule verification."""

        return self.verifier_mode in {
            RULE_ONLY_MODE,
            HYBRID_MODE,
        }

    @property
    def uses_llm_verifier(self) -> bool:
        """Return whether the configured mode uses LLM verification."""

        return self.verifier_mode in {
            LLM_ONLY_MODE,
            HYBRID_MODE,
        }


def normalize_verifier_mode(
    value: Optional[str],
) -> str:
    """Normalize and validate a verifier mode value.

    Empty or missing values use the safe default ``rule_only``.

    Raises:
        ConfigurationError: If the supplied mode is unsupported.
    """

    if value is None or not value.strip():
        return DEFAULT_VERIFIER_MODE

    normalized_mode = value.strip().lower()

    if normalized_mode not in SUPPORTED_VERIFIER_MODES:
        supported_modes = ", ".join(
            sorted(SUPPORTED_VERIFIER_MODES)
        )

        raise ConfigurationError(
            f"Unsupported verifier mode '{value}'. "
            f"Supported modes: {supported_modes}"
        )

    return normalized_mode


def load_app_config(
    environ: Optional[Mapping[str, str]] = None,
) -> AppConfig:
    """Load and validate application configuration.

    Args:
        environ: Optional environment-variable mapping. Supplying a mapping
            makes configuration behavior easy to test without modifying the
            real process environment.
    """

    environment = os.environ if environ is None else environ

    verifier_mode = normalize_verifier_mode(
        environment.get(VERIFIER_MODE_ENV)
    )

    return AppConfig(
        verifier_mode=verifier_mode,
    )
