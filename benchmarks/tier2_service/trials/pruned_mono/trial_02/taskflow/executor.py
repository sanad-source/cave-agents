"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

import threading
import time
from typing import Any, Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    def __init__(
        self,
        queue: PriorityTaskQueue,
        storage: Optional[Any] = None,
        num_workers: int = 4,
    ) -> None:
        if isinstance(storage, int):
            num_workers = storage
            storage = None
        self._queue = queue
        self._storage: Optional[JobStorage] = storage
        self._num_workers = num_workers
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._threads: list[threading.Thread] = []
        self._running = False
        self._lock = threading.RLock()
        self._active_workers = 0

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def get_active_workers(self) -> int:
        return self.active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

    def _notify_listeners(self, event: str, job: Job) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._threads = []
            for i in range(self._num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"taskflow-worker-{i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            threads = list(self._threads)

        if wait:
            deadline = time.time() + (timeout if timeout is not None else 5.0)
            for t in threads:
                rem = deadline - time.time()
                if rem > 0:
                    t.join(timeout=rem)

        with self._lock:
            self._threads = []

    def _worker_loop(self) -> None:
        while self._running:
            job = self._queue.pop(timeout=0.2)
            if job is None:
                continue

            if job.status == JobStatus.CANCELLED:
                continue

            with self._lock:
                self._active_workers += 1

            try:
                self._process_job(job)
            finally:
                with self._lock:
                    self._active_workers -= 1

    def _process_job(self, job: Job) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self._storage:
            self._storage.update_status(job.job_id, JobStatus.RUNNING)
        self._notify_listeners("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            error_msg = f"No handler registered for function '{job.fn_name}'"
            self._handle_failure(job, RuntimeError(error_msg))
            return

        timed_out = False
        exc = None
        result = None

        if job.timeout is not None and job.timeout > 0:
            res_box = []
            exc_box = []

            def target() -> None:
                try:
                    res_box.append(handler(*job.args, **job.kwargs))
                except BaseException as e:
                    exc_box.append(e)

            worker_thread = threading.Thread(target=target, daemon=True)
            worker_thread.start()
            worker_thread.join(timeout=job.timeout)

            if worker_thread.is_alive():
                timed_out = True
                error_msg = f"Job exceeded execution timeout of {job.timeout} seconds"
            elif exc_box:
                exc = exc_box[0]
            elif res_box:
                result = res_box[0]
        else:
            try:
                result = handler(*job.args, **job.kwargs)
            except BaseException as e:
                exc = e

        if job.status == JobStatus.CANCELLED:
            return

        if timed_out:
            job.status = JobStatus.FAILED
            job.error = error_msg
            if self._storage:
                self._storage.update_status(job.job_id, JobStatus.FAILED, error=error_msg)
            self._notify_listeners("on_failure", job)
            return

        if exc is not None:
            self._handle_failure(job, exc)
            return

        job.status = JobStatus.COMPLETED
        job.result = result
        job.error = None
        if self._storage:
            self._storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
        self._notify_listeners("on_success", job)

    def _handle_failure(self, job: Job, exc: BaseException) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        error_str = str(exc) or repr(exc)
        job.error = error_str

        if job.retry_policy and job.attempts < job.retry_policy.max_attempts:
            job.status = JobStatus.RETRYING
            delay = job.retry_policy.get_delay(job.attempts)
            job.scheduled_at = time.time() + delay
            if self._storage:
                self._storage.update_status(job.job_id, JobStatus.RETRYING, error=error_str)
            self._queue.push(job)
            self._notify_listeners("on_retry", job)
        else:
            job.status = JobStatus.FAILED
            if self._storage:
                self._storage.update_status(job.job_id, JobStatus.FAILED, error=error_str)
            self._notify_listeners("on_failure", job)
