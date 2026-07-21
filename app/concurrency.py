"""Thread-safe verification concurrency protection."""

import threading
import time
from contextlib import contextmanager
from typing import Iterator

from app.config import (
    DEFAULT_MAX_CONCURRENT_VERIFICATIONS,
    DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS,
)
from app.metrics import (
    record_verification_finished,
    record_verification_queue_wait,
    record_verification_rejected,
    record_verification_started,
)


class VerificationOverloadedError(RuntimeError):
    """Raised when no verification slot becomes available."""


class VerificationConcurrencyController:
    """Bound concurrent verification execution per process."""

    def __init__(
        self,
        *,
        max_concurrent: int,
        queue_timeout_seconds: float,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError(
                "max_concurrent must be greater than zero."
            )

        if queue_timeout_seconds <= 0:
            raise ValueError(
                "queue_timeout_seconds must be greater than zero."
            )

        self.max_concurrent = int(max_concurrent)
        self.queue_timeout_seconds = float(
            queue_timeout_seconds
        )

        self._semaphore = threading.BoundedSemaphore(
            self.max_concurrent
        )

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Acquire one bounded verification execution slot."""

        started_waiting = time.perf_counter()

        acquired = self._semaphore.acquire(
            timeout=self.queue_timeout_seconds
        )

        waited_seconds = (
            time.perf_counter()
            - started_waiting
        )

        record_verification_queue_wait(
            waited_seconds
        )

        if not acquired:
            record_verification_rejected()

            raise VerificationOverloadedError(
                "Verification capacity is currently exhausted."
            )

        record_verification_started()

        try:
            yield
        finally:
            record_verification_finished()
            self._semaphore.release()


_controller_lock = threading.Lock()

_controller = VerificationConcurrencyController(
    max_concurrent=(
        DEFAULT_MAX_CONCURRENT_VERIFICATIONS
    ),
    queue_timeout_seconds=(
        DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS
    ),
)


def configure_verification_concurrency(
    *,
    max_concurrent: int,
    queue_timeout_seconds: float,
) -> None:
    """Replace the process-local concurrency controller."""

    global _controller

    replacement = VerificationConcurrencyController(
        max_concurrent=max_concurrent,
        queue_timeout_seconds=queue_timeout_seconds,
    )

    with _controller_lock:
        _controller = replacement


def get_verification_concurrency_controller(
) -> VerificationConcurrencyController:
    """Return the currently configured controller."""

    with _controller_lock:
        return _controller
