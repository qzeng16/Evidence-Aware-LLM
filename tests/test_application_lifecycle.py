"""Tests for application lifespan and graceful shutdown."""

import asyncio
import threading
import time

import pytest
from fastapi import FastAPI

import app.lifecycle as lifecycle
from app.concurrency import (
    VerificationConcurrencyController,
)
from app.config import (
    AppConfig,
    ConfigurationError,
    load_app_config,
)
from app.execution import (
    VerificationExecutionManager,
    VerificationExecutionUnavailableError,
    VerificationTimeoutError,
)


def test_configuration_loads_graceful_shutdown_timeout():
    config = load_app_config(
        {
            (
                "GRACEFUL_SHUTDOWN_"
                "TIMEOUT_SECONDS"
            ): "12.5",
        }
    )

    assert (
        config.graceful_shutdown_timeout_seconds
        == 12.5
    )


def test_configuration_rejects_invalid_shutdown_timeout():
    with pytest.raises(
        ConfigurationError,
        match="greater than zero",
    ):
        load_app_config(
            {
                (
                    "GRACEFUL_SHUTDOWN_"
                    "TIMEOUT_SECONDS"
                ): "0",
            }
        )


def test_shutdown_rejects_new_work_and_releases_lease():
    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.02,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=1.0,
    )

    manager.begin_shutdown()

    lease = controller.acquire()

    with pytest.raises(
        VerificationExecutionUnavailableError
    ):
        manager.execute(
            lambda: "must-not-run",
            lease=lease,
        )

    replacement_lease = controller.acquire()
    replacement_lease.release()

    assert manager.accepting is False
    assert manager.active_tasks == 0
    assert manager.shutdown(0.0) is True


def test_shutdown_waits_for_timed_out_background_task():
    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.02,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=0.03,
    )

    started = threading.Event()
    release = threading.Event()

    def slow_work():
        started.set()

        assert release.wait(
            timeout=2.0
        )

        return "complete"

    lease = controller.acquire()

    with pytest.raises(
        VerificationTimeoutError
    ):
        manager.execute(
            slow_work,
            lease=lease,
        )

    assert started.is_set()
    assert manager.active_tasks == 1

    timer = threading.Timer(
        0.12,
        release.set,
    )

    timer.start()

    started_shutdown = time.monotonic()

    drained = manager.shutdown(
        timeout_seconds=1.0
    )

    shutdown_elapsed = (
        time.monotonic()
        - started_shutdown
    )

    timer.join(
        timeout=1.0
    )

    assert drained is True
    assert shutdown_elapsed >= 0.08
    assert manager.active_tasks == 0
    assert manager.accepting is False


def test_shutdown_deadline_reports_undrained_work():
    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.02,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=0.02,
    )

    release = threading.Event()

    def slow_work():
        assert release.wait(
            timeout=2.0
        )

    lease = controller.acquire()

    with pytest.raises(
        VerificationTimeoutError
    ):
        manager.execute(
            slow_work,
            lease=lease,
        )

    drained = manager.shutdown(
        timeout_seconds=0.01
    )

    assert drained is False
    assert manager.active_tasks == 1
    assert manager.accepting is False

    release.set()

    deadline = time.monotonic() + 2.0

    while manager.active_tasks != 0:
        if time.monotonic() >= deadline:
            raise AssertionError(
                "Background task did not finish."
            )

        time.sleep(0.01)

    assert manager.active_tasks == 0


def test_application_lifespan_orders_startup_and_shutdown(
    monkeypatch,
):
    events = []

    config = AppConfig(
        graceful_shutdown_timeout_seconds=4.5,
    )

    monkeypatch.setattr(
        lifecycle,
        "initialize_service",
        lambda: events.append(
            "initialize"
        ),
    )

    monkeypatch.setattr(
        lifecycle,
        "get_app_config",
        lambda: config,
    )

    def fake_shutdown(timeout_seconds):
        events.append(
            (
                "shutdown",
                timeout_seconds,
            )
        )

        return True

    monkeypatch.setattr(
        lifecycle,
        "shutdown_verification_execution",
        fake_shutdown,
    )

    monkeypatch.setattr(
        lifecycle,
        "reset_service_state",
        lambda: events.append(
            "reset"
        ),
    )

    app = FastAPI()

    async def run_lifespan():
        async with lifecycle.application_lifespan(
            app
        ):
            events.append("serving")

            assert (
                app.state.accepting_verifications
                is True
            )

        assert (
            app.state.accepting_verifications
            is False
        )

        assert (
            app.state.verification_shutdown_drained
            is True
        )

    asyncio.run(
        run_lifespan()
    )

    assert events == [
        "initialize",
        "serving",
        (
            "shutdown",
            4.5,
        ),
        "reset",
    ]


def test_verifier_timeout_error_is_not_execution_timeout():
    """A verifier-raised TimeoutError must propagate unchanged."""

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.02,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=1.0,
    )

    def provider_timeout():
        raise TimeoutError(
            "Provider connection timed out."
        )

    lease = controller.acquire()

    with pytest.raises(
        TimeoutError,
        match="Provider connection timed out",
    ):
        manager.execute(
            provider_timeout,
            lease=lease,
        )

    assert manager.active_tasks == 0

    replacement_lease = controller.acquire()
    replacement_lease.release()

    assert manager.shutdown(0.0) is True


def test_main_uses_lifespan_without_deprecated_events():
    from pathlib import Path

    main_text = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "lifespan=application_lifespan"
        in main_text
    )

    assert "@app.on_event" not in main_text
    assert "startup_event" not in main_text
