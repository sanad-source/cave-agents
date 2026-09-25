"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class _JobTimeoutException(TimeoutError):
    """Raised when job execution exceeds configured timeout."""
    pass


class WorkerPool:
    """Multi-threaded worker pool executing queued tasks with retry and timeout support."""

    VALID_EVENTS = {"on_start", "on_success", "on_failure", "on_retry"}

    def __init__(
        self,
        queue: Optional[Any] = None,
        storage: Optional[Any] = None,
        num_workers: int = 4,
        **kwargs: Any,
    ) -> None:
        if isinstance(queue, int):
            num_workers = queue
            queue = kwargs.get("queue", None)
            storage = kwargs.get("storage", None)
        elif isinstance(storage, int):
            num_workers = storage
            storage = kwargs.get("storage", None)

        if "num_workers" in kwargs:
            num_workers = kwargs["num_workers"]

        self.num_workers: int = int(num_workers)
        if queue is not None and not isinstance(queue, int):
            self.queue = queue
        else:
            self.queue = PriorityTaskQueue()

        if storage is not None and not isinstance(storage, int):
            self.storage: Optional[JobStorage] = storage
        else:
            self.storage = None

        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        self._listener_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._is_running: bool = False
        self._workers: List[threading.Thread] = []

        self._active_workers: int = 0
        self._active_lock = threading.Lock()

        self._listeners: Dict[str, List[Callable[[Job], None]]] = {
            event: [] for event in self.VALID_EVENTS
        }

    @property
    def active_workers(self) -> int:
        """Return the count of currently active worker threads executing jobs."""
        with self._active_lock:
            return self._active_workers

    @property
    def is_running(self) -> bool:
        """Return True if worker pool is currently running."""
        with self._lifecycle_lock:
            return self._is_running

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a handler callable by function name."""
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener callback for a valid lifecycle event."""
        if event not in self.VALID_EVENTS:
            raise ValueError(f"Unknown event: '{event}'. Supported events: {self.VALID_EVENTS}")
        with self._listener_lock:
            self._listeners[event].append(callback)

    def remove_listener(self, event: str, callback: Callable[[Job], None]) -> bool:
        """Remove a registered event listener callback. Return True if found and removed."""
        with self._listener_lock:
            callbacks = self._listeners.get(event, [])
            if callback in callbacks:
                callbacks.remove(callback)
                return True
            return False

    def _notify_listeners(self, event: str, job: Job) -> None:
        """Safely notify all registered listeners for an event."""
        with self._listener_lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def start(self) -> None:
        """Start worker threads."""
        with self._lifecycle_lock:
            if self._is_running:
                return
            self._stop_event.clear()
            self._is_running = True
            self._workers = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-Worker-{i+1}",
                    daemon=True,
                )
                self._workers.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signal workers to stop and optionally wait for termination up to timeout seconds."""
        with self._lifecycle_lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()
            workers = list(self._workers)

        if wait and workers:
            deadline = (time.time() + timeout) if timeout is not None else None
            for t in workers:
                if deadline is not None:
                    rem = max(0.0, deadline - time.time())
                else:
                    rem = None
                t.join(timeout=rem)

    def stop(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Alias for shutdown."""
        self.shutdown(wait=wait, timeout=timeout)

    def _worker_loop(self) -> None:
        """Main execution loop for worker daemon threads."""
        while not self._stop_event.is_set():
            try:
                job = self.queue.pop(timeout=0.1)
            except Exception:
                continue

            if job is None:
                continue

            if self._is_cancelled(job):
                continue

            with self._active_lock:
                self._active_workers += 1

            try:
                self._execute_job(job)
            except Exception:
                pass
            finally:
                with self._active_lock:
                    self._active_workers -= 1

    def _execute_job(self, job: Job) -> None:
        """Execute a single job with status tracking, timeout, and retries."""
        if self._is_cancelled(job):
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.RUNNING)

        self._notify_listeners("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            exc = KeyError(f"No handler registered for function '{job.fn_name}'")
            self._handle_failure(job, exc)
            return

        try:
            if job.timeout is not None:
                if job.timeout <= 0:
                    raise _JobTimeoutException(f"Job execution exceeded timeout of {job.timeout}s")
                result = self._run_with_timeout(handler, job.args, job.kwargs, job.timeout)
            else:
                result = handler(*job.args, **job.kwargs)
        except _JobTimeoutException as exc:
            self._handle_timeout(job, exc)
        except Exception as exc:
            self._handle_failure(job, exc)
        else:
            self._handle_success(job, result)

    def _run_with_timeout(self, fn: Callable, args: tuple, kwargs: dict, timeout: float) -> Any:
        """Run callable in a separate thread and enforce timeout."""
        outcome: Dict[str, Any] = {}
        done = threading.Event()

        def target() -> None:
            try:
                outcome["result"] = fn(*args, **kwargs)
            except BaseException as e:
                outcome["error"] = e
            finally:
                done.set()

        t = threading.Thread(target=target, daemon=True)
        t.start()
        finished = done.wait(timeout=timeout)
        if not finished:
            raise _JobTimeoutException(f"Job execution exceeded timeout of {timeout}s")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("result")

    def _is_cancelled(self, job: Job) -> bool:
        """Check if job was marked as CANCELLED in object or storage."""
        if job.status == JobStatus.CANCELLED:
            return True
        if self.storage is not None:
            stored = self.storage.get_job(job.job_id)
            if stored is not None and stored.status == JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
                return True
        return False

    def _handle_timeout(self, job: Job, exc: _JobTimeoutException) -> None:
        """Handle execution timeout by failing job directly without retry."""
        if self._is_cancelled(job):
            return
        job.status = JobStatus.FAILED
        job.error = str(exc)
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
        self._notify_listeners("on_failure", job)

    def _handle_failure(self, job: Job, exc: Exception) -> None:
        """Handle execution failure with exponential backoff retry or terminal failure."""
        if self._is_cancelled(job):
            return
        err_msg = str(exc)
        if not err_msg:
            err_msg = type(exc).__name__
        job.error = err_msg

        if job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
            job.status = JobStatus.RETRYING
            delay = job.retry_policy.get_delay(job.attempts)
            job.scheduled_at = time.time() + delay
            if self.storage is not None:
                self.storage.update_status(job.job_id, JobStatus.RETRYING, error=job.error)
            self.queue.push(job)
            self._notify_listeners("on_retry", job)
        else:
            job.status = JobStatus.FAILED
            if self.storage is not None:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
            self._notify_listeners("on_failure", job)

    def _handle_success(self, job: Job, result: Any) -> None:
        """Handle successful execution by updating result and status to COMPLETED."""
        if self._is_cancelled(job):
            return
        job.status = JobStatus.COMPLETED
        job.result = result
        job.error = None
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
        self._notify_listeners("on_success", job)

    def __enter__(self) -> WorkerPool:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()
