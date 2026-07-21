"""Validated application configuration."""

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional


VERIFIER_MODE_ENV = "VERIFIER_MODE"

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
OPENAI_TIMEOUT_SECONDS_ENV = (
    "OPENAI_TIMEOUT_SECONDS"
)
OPENAI_MAX_RETRIES_ENV = "OPENAI_MAX_RETRIES"

MAX_CONCURRENT_VERIFICATIONS_ENV = (
    "MAX_CONCURRENT_VERIFICATIONS"
)

VERIFICATION_QUEUE_TIMEOUT_SECONDS_ENV = (
    "VERIFICATION_QUEUE_TIMEOUT_SECONDS"
)

MAX_REQUEST_BODY_BYTES_ENV = (
    "MAX_REQUEST_BODY_BYTES"
)

MAX_CLAIM_LENGTH_ENV = "MAX_CLAIM_LENGTH"

VERIFICATION_TIMEOUT_SECONDS_ENV = (
    "VERIFICATION_TIMEOUT_SECONDS"
)

GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS_ENV = (
    "GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS"
)


RULE_ONLY_MODE = "rule_only"
LLM_ONLY_MODE = "llm_only"
HYBRID_MODE = "hybrid"

DEFAULT_VERIFIER_MODE = RULE_ONLY_MODE
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
DEFAULT_OPENAI_MAX_RETRIES = 2

DEFAULT_MAX_CONCURRENT_VERIFICATIONS = 4

DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS = 0.5

DEFAULT_MAX_REQUEST_BODY_BYTES = 16384
DEFAULT_MAX_CLAIM_LENGTH = 4000

DEFAULT_VERIFICATION_TIMEOUT_SECONDS = 30.0

DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 30.0


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

    openai_api_key: Optional[str] = field(
        default=None,
        repr=False,
    )

    openai_model: str = DEFAULT_OPENAI_MODEL

    openai_timeout_seconds: float = (
        DEFAULT_OPENAI_TIMEOUT_SECONDS
    )

    openai_max_retries: int = (
        DEFAULT_OPENAI_MAX_RETRIES
    )

    max_concurrent_verifications: int = (
        DEFAULT_MAX_CONCURRENT_VERIFICATIONS
    )

    verification_queue_timeout_seconds: float = (
        DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS
    )

    max_request_body_bytes: int = (
        DEFAULT_MAX_REQUEST_BODY_BYTES
    )

    max_claim_length: int = (
        DEFAULT_MAX_CLAIM_LENGTH
    )

    verification_timeout_seconds: float = (
        DEFAULT_VERIFICATION_TIMEOUT_SECONDS
    )

    graceful_shutdown_timeout_seconds: float = (
        DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
    )

    @property
    def uses_rule_verifier(self) -> bool:
        """Return whether rule verification is enabled."""

        return self.verifier_mode in {
            RULE_ONLY_MODE,
            HYBRID_MODE,
        }

    @property
    def uses_llm_verifier(self) -> bool:
        """Return whether LLM verification is enabled."""

        return self.verifier_mode in {
            LLM_ONLY_MODE,
            HYBRID_MODE,
        }

    @property
    def has_openai_api_key(self) -> bool:
        """Return whether an API key was configured."""

        return self.openai_api_key is not None


def normalize_verifier_mode(
    value: Optional[str],
) -> str:
    """Normalize and validate the verifier mode."""

    if value is None or not value.strip():
        return DEFAULT_VERIFIER_MODE

    normalized_mode = value.strip().lower()

    if normalized_mode not in (
        SUPPORTED_VERIFIER_MODES
    ):
        supported_modes = ", ".join(
            sorted(SUPPORTED_VERIFIER_MODES)
        )

        raise ConfigurationError(
            f"Unsupported verifier mode '{value}'. "
            f"Supported modes: {supported_modes}"
        )

    return normalized_mode


def normalize_openai_api_key(
    value: Optional[str],
) -> Optional[str]:
    """Normalize an optional OpenAI API key."""

    if value is None:
        return None

    normalized_value = value.strip()

    if not normalized_value:
        return None

    return normalized_value


def normalize_openai_model(
    value: Optional[str],
) -> str:
    """Normalize the configured OpenAI model."""

    if value is None or not value.strip():
        return DEFAULT_OPENAI_MODEL

    return value.strip()


def normalize_positive_float(
    value: Optional[str],
    default: float,
    field_name: str,
) -> float:
    """Normalize a positive floating-point setting."""

    if value is None or not value.strip():
        return default

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"{field_name} must be a number."
        ) from error

    if normalized_value <= 0:
        raise ConfigurationError(
            f"{field_name} must be greater than zero."
        )

    return normalized_value


def normalize_positive_integer(
    value: Optional[str],
    default: int,
    field_name: str,
) -> int:
    """Normalize a strictly positive integer setting."""

    if value is None or not value.strip():
        return default

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"{field_name} must be an integer."
        ) from error

    if normalized_value <= 0:
        raise ConfigurationError(
            f"{field_name} must be greater than zero."
        )

    return normalized_value


def normalize_nonnegative_integer(
    value: Optional[str],
    default: int,
    field_name: str,
) -> int:
    """Normalize a nonnegative integer setting."""

    if value is None or not value.strip():
        return default

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"{field_name} must be an integer."
        ) from error

    if normalized_value < 0:
        raise ConfigurationError(
            f"{field_name} cannot be negative."
        )

    return normalized_value


def load_app_config(
    environ: Optional[
        Mapping[str, str]
    ] = None,
) -> AppConfig:
    """Load application configuration from environment variables."""

    environment = (
        os.environ
        if environ is None
        else environ
    )

    return AppConfig(
        verifier_mode=normalize_verifier_mode(
            environment.get(
                VERIFIER_MODE_ENV
            )
        ),
        openai_api_key=normalize_openai_api_key(
            environment.get(
                OPENAI_API_KEY_ENV
            )
        ),
        openai_model=normalize_openai_model(
            environment.get(
                OPENAI_MODEL_ENV
            )
        ),
        openai_timeout_seconds=(
            normalize_positive_float(
                environment.get(
                    OPENAI_TIMEOUT_SECONDS_ENV
                ),
                default=(
                    DEFAULT_OPENAI_TIMEOUT_SECONDS
                ),
                field_name=(
                    OPENAI_TIMEOUT_SECONDS_ENV
                ),
            )
        ),
        openai_max_retries=(
            normalize_nonnegative_integer(
                environment.get(
                    OPENAI_MAX_RETRIES_ENV
                ),
                default=(
                    DEFAULT_OPENAI_MAX_RETRIES
                ),
                field_name=(
                    OPENAI_MAX_RETRIES_ENV
                ),
            )
        ),
        max_concurrent_verifications=(
            normalize_positive_integer(
                environment.get(
                    MAX_CONCURRENT_VERIFICATIONS_ENV
                ),
                default=(
                    DEFAULT_MAX_CONCURRENT_VERIFICATIONS
                ),
                field_name=(
                    MAX_CONCURRENT_VERIFICATIONS_ENV
                ),
            )
        ),
        verification_queue_timeout_seconds=(
            normalize_positive_float(
                environment.get(
                    VERIFICATION_QUEUE_TIMEOUT_SECONDS_ENV
                ),
                default=(
                    DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS
                ),
                field_name=(
                    VERIFICATION_QUEUE_TIMEOUT_SECONDS_ENV
                ),
            )
        ),
        max_request_body_bytes=(
            normalize_positive_integer(
                environment.get(
                    MAX_REQUEST_BODY_BYTES_ENV
                ),
                default=(
                    DEFAULT_MAX_REQUEST_BODY_BYTES
                ),
                field_name=(
                    MAX_REQUEST_BODY_BYTES_ENV
                ),
            )
        ),
        max_claim_length=(
            normalize_positive_integer(
                environment.get(
                    MAX_CLAIM_LENGTH_ENV
                ),
                default=(
                    DEFAULT_MAX_CLAIM_LENGTH
                ),
                field_name=(
                    MAX_CLAIM_LENGTH_ENV
                ),
            )
        ),
        verification_timeout_seconds=(
            normalize_positive_float(
                environment.get(
                    VERIFICATION_TIMEOUT_SECONDS_ENV
                ),
                default=(
                    DEFAULT_VERIFICATION_TIMEOUT_SECONDS
                ),
                field_name=(
                    VERIFICATION_TIMEOUT_SECONDS_ENV
                ),
            )
        ),
        graceful_shutdown_timeout_seconds=(
            normalize_positive_float(
                environment.get(
                    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS_ENV
                ),
                default=(
                    DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
                ),
                field_name=(
                    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS_ENV
                ),
            )
        ),
    )
