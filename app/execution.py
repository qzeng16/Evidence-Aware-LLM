"""Bounded background execution for verification requests."""

import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    wait,
)
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    TypeVar,
)

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


class VerificationExecutionUnavailableError(
    RuntimeError
):
    """Raised after the executor stops accepting new work."""


class VerificationExecutionManager:
    """Execute verifier work with timeout and shutdown safety."""

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

        self._condition = threading.Condition()
        self._accepting = True
        self._active_tasks = 0
        self._executor_shutdown = False

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="verification",
        )

    @property
    def accepting(self) -> bool:
        """Report whether new tasks are accepted."""

        with self._condition:
            return self._accepting

    @property
    def active_tasks(self) -> int:
        """Return the number of submitted unfinished tasks."""

        with self._condition:
            return self._active_tasks

    def _finish_task(self) -> None:
        """Record that one submitted task has really finished."""

        with self._condition:
            self._active_tasks -= 1

            if self._active_tasks < 0:
                self._active_tasks = 0

            self._condition.notify_all()

    def _run_with_lease(
        self,
        function: Callable[..., ResultType],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        lease: VerificationLease,
    ) -> ResultType:
        """Run work and release resources only after completion."""

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
            self._finish_task()

    def execute(
        self,
        function: Callable[..., ResultType],
        *args: Any,
        lease: VerificationLease,
        **kwargs: Any
    ) -> ResultType:
        """Submit work and wait only up to the HTTP timeout."""

        with self._condition:
            if (
                not self._accepting
                or self._executor_shutdown
            ):
                lease.release()

                raise (
                    VerificationExecutionUnavailableError(
                        "Verification execution is shutting down."
                    )
                )

            self._active_tasks += 1

            try:
                future = self._executor.submit(
                    self._run_with_lease,
                    function,
                    args,
                    kwargs,
                    lease,
                )
            except BaseException:
                self._active_tasks -= 1
                self._condition.notify_all()
                lease.release()
                raise

        completed, _ = wait(
            (future,),
            timeout=self.timeout_seconds,
        )

        if not completed:
            record_verification_timeout()

            raise VerificationTimeoutError(
                "Verification execution exceeded "
                "the configured timeout."
            )

        return future.result()

    def begin_shutdown(self) -> None:
        """Atomically stop accepting new verification tasks."""

        with self._condition:
            self._accepting = False
            self._condition.notify_all()

    def wait_for_idle(
        self,
        timeout_seconds: Optional[float],
    ) -> bool:
        """Wait for submitted tasks to finish within a deadline."""

        deadline = None

        if timeout_seconds is not None:
            deadline = (
                time.monotonic()
                + max(
                    float(timeout_seconds),
                    0.0,
                )
            )

        with self._condition:
            while self._active_tasks > 0:
                if deadline is None:
                    self._condition.wait()
                    continue

                remaining_seconds = (
                    deadline
                    - time.monotonic()
                )

                if remaining_seconds <= 0:
                    return False

                self._condition.wait(
                    timeout=remaining_seconds
                )

            return True

    def shutdown(
        self,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Stop submissions and drain work when possible."""

        self.begin_shutdown()

        drained = self.wait_for_idle(
            timeout_seconds
        )

        should_shutdown_executor = False

        with self._condition:
            if not self._executor_shutdown:
                self._executor_shutdown = True
                should_shutdown_executor = True

        if should_shutdown_executor:
            self._executor.shutdown(
                wait=drained,
                cancel_futures=False,
            )

        return drained


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

    previous.shutdown(
        timeout_seconds=0.0
    )


def get_verification_execution_manager(
) -> VerificationExecutionManager:
    """Return the active process-local execution manager."""

    with _manager_lock:
        return _manager


def shutdown_verification_execution(
    timeout_seconds: float,
) -> bool:
    """Gracefully stop the active verification executor."""

    manager = (
        get_verification_execution_manager()
    )

    return manager.shutdown(
        timeout_seconds=timeout_seconds
    )
