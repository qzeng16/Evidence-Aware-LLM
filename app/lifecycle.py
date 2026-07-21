"""FastAPI application startup and shutdown lifecycle."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import (
    DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
)
from app.execution import (
    shutdown_verification_execution,
)
from app.services import (
    get_app_config,
    initialize_service,
    reset_service_state,
)


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Initialize runtime resources and clean them up safely."""

    initialize_service()

    config = get_app_config()

    app.state.accepting_verifications = True
    app.state.verification_shutdown_drained = None

    try:
        yield
    finally:
        app.state.accepting_verifications = False

        shutdown_timeout_seconds = (
            DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
        )

        if config is not None:
            shutdown_timeout_seconds = (
                config.graceful_shutdown_timeout_seconds
            )

        drained = shutdown_verification_execution(
            shutdown_timeout_seconds
        )

        app.state.verification_shutdown_drained = (
            drained
        )

        reset_service_state()
