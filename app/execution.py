"""Bounded background execution for verification requests."""

import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from typing import Any, Callable, Dict, TypeVar

from app.concurrency import VerificationLease
from app.config import (
    DEFAULT_MAX_CONCURRENT_VERIFICATIONS,
    DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
)
from app.metrics import (
    record_verification_execution_duration,
    record_verification_timeout,
)


ResultType = TypeVar("ResultType")


class VerificationTimeoutError(RuntimeError):
    """Raised when HTTP waiting exceeds the configured timeout."""


class VerificationExecutionManager:
    """Execute verifier calls without releasing timed-out slots early."""

    def __init__(
        self,
        *,
        max_workers: int,
        timeout_seconds: float,
    ) -> None:
        if max_workers <= 0:
            raise ValueError(
                "max_workers must be greater than zero."
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.max_workers = int(max_workers)
        self.timeout_seconds = float(
            timeout_seconds
        )

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="verification",
        )

    @staticmethod
    def _run_with_lease(
        function: Callable[..., ResultType],
        args: tuple,
        kwargs: Dict[str, Any],
        lease: VerificationLease,
    ) -> ResultType:
        """Run one task and release its slot after real completion."""

        started_at = time.perf_counter()

        try:
            return function(
                *args,
                **kwargs
            )
        finally:
            duration_seconds = (
                time.perf_counter()
                - started_at
            )

            record_verification_execution_duration(
                duration_seconds
            )

            lease.release()

    def execute(
        self,
        function: Callable[..., ResultType],
        *args: Any,
        lease: VerificationLease,
        **kwargs: Any
    ) -> ResultType:
        """Wait for a result only up to the HTTP timeout."""

        try:
            future = self._executor.submit(
                self._run_with_lease,
                function,
                args,
                kwargs,
                lease,
            )
        except BaseException:
            lease.release()
            raise

        try:
            return future.result(
                timeout=self.timeout_seconds
            )
        except FutureTimeoutError as error:
            record_verification_timeout()

            raise VerificationTimeoutError(
                "Verification execution exceeded "
                "the configured timeout."
            ) from error

    def shutdown(self) -> None:
        """Stop accepting new background work."""

        self._executor.shutdown(
            wait=False,
            cancel_futures=False,
        )


_manager_lock = threading.Lock()

_manager = VerificationExecutionManager(
    max_workers=(
        DEFAULT_MAX_CONCURRENT_VERIFICATIONS
    ),
    timeout_seconds=(
        DEFAULT_VERIFICATION_TIMEOUT_SECONDS
    ),
)


def configure_verification_execution(
    *,
    max_workers: int,
    timeout_seconds: float,
) -> None:
    """Replace the process-local execution manager."""

    global _manager

    replacement = VerificationExecutionManager(
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
    )

    with _manager_lock:
        previous = _manager
        _manager = replacement

    previous.shutdown()


def get_verification_execution_manager(
) -> VerificationExecutionManager:
    """Return the active process-local execution manager."""

    with _manager_lock:
        return _manager
