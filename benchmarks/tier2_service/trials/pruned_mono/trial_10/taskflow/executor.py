"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

import threading
import time
from typing import Callable, Optional

from .models import Job, JobStatus
from .queue import PriorityTaskQueue
from .storage import JobStorage


class WorkerPool:
    """Multi-threaded worker pool executing jobs from PriorityTaskQueue."""

    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ):
        if isinstance(queue, int):
            num_workers = queue
            queue = None
        self.queue = queue if queue is not None else PriorityTaskQueue()
        self.num_workers = num_workers
        self.storage = storage
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._threads: list[threading.Thread] = []
        self._running = False
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._active_count = 0
        self._active_lock = threading.Lock()

    @property
    def active_workers(self) -> int:
        with self._active_lock:
            return self._active_count

    @property
    def active_workers_count(self) -> int:
        with self._active_lock:
            return self._active_count

    def register_handler(self, name: str, fn: Callable) -> None:
        """Registers callable by name."""
        self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register event listener for 'on_start', 'on_success', 'on_failure', 'on_retry'."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def _fire_event(self, event: str, job: Job) -> None:
        callbacks = list(self._listeners.get(event, []))
        for callback in callbacks:
            try:
                callback(job)
            except Exception:
                pass

    def _execute_job(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self.storage:
            self.storage.update_status(job.job_id, JobStatus.RUNNING)
        self._fire_event("on_start", job)

        handler = self._handlers.get(job.fn_name)
        if handler is None:
            err = f"No handler registered for '{job.fn_name}'"
            job.status = JobStatus.FAILED
            job.error = err
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=err)
            self._fire_event("on_failure", job)
            return

        is_timeout = False
        try:
            if job.timeout is not None and job.timeout > 0:
                result_box = []
                err_box = []
                done_evt = threading.Event()

                def target():
                    try:
                        result_box.append(handler(*job.args, **job.kwargs))
                    except Exception as ex:
                        err_box.append(ex)
                    finally:
                        done_evt.set()

                t = threading.Thread(target=target, daemon=True)
                t.start()
                if not done_evt.wait(timeout=job.timeout):
                    is_timeout = True
                    raise TimeoutError(
                        f"Job execution timed out: exceeded timeout of {job.timeout} seconds"
                    )
                if err_box:
                    raise err_box[0]
                result = result_box[0] if result_box else None
            else:
                result = handler(*job.args, **job.kwargs)

            job.status = JobStatus.COMPLETED
            job.result = result
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
            self._fire_event("on_success", job)

        except Exception as e:
            if is_timeout:
                job.status = JobStatus.FAILED
                job.error = str(e)
                if self.storage:
                    self.storage.update_status(
                        job.job_id, JobStatus.FAILED, error=job.error
                    )
                self._fire_event("on_failure", job)
            elif job.retry_policy and job.attempts < job.retry_policy.max_attempts:
                job.status = JobStatus.RETRYING
                delay = job.retry_policy.get_delay(job.attempts)
                job.scheduled_at = time.time() + delay
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.RETRYING)
                self.queue.push(job)
                self._fire_event("on_retry", job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(e)
                if self.storage:
                    self.storage.update_status(
                        job.job_id, JobStatus.FAILED, error=job.error
                    )
                self._fire_event("on_failure", job)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self.queue.pop(timeout=0.1)
            if job is None:
                continue
            if job.status == JobStatus.CANCELLED:
                continue
            with self._active_lock:
                self._active_count += 1
            try:
                self._execute_job(job)
            finally:
                with self._active_lock:
                    self._active_count -= 1

    def start(self) -> None:
        """Starts worker threads."""
        with self._lifecycle_lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-{i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signals workers to stop. If wait is True, waits up to timeout seconds for running jobs to complete."""
        with self._lifecycle_lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            threads = list(self._threads)

        if wait:
            deadline = (time.time() + timeout) if timeout is not None else float("inf")
            for t in threads:
                remaining = max(0.0, deadline - time.time())
                t.join(timeout=remaining)
