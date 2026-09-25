from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any, Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        storage: Optional[JobStorage] = None,
        num_workers: int = 4,
    ) -> None:
        if isinstance(queue, int):
            num_workers = queue
            queue = None
        self.queue = queue if queue is not None else PriorityTaskQueue()
        self.storage = storage
        self.num_workers = num_workers
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._lock = threading.RLock()
        self._active_workers = 0
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._started = False
        self._timeout_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(self.num_workers * 4, 16)
        )

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        with self._lock:
            if event in self._listeners:
                self._listeners[event].append(callback)
            else:
                self._listeners[event] = [callback]

    def _fire_event(self, event: str, job: Job) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def _run_with_timeout(
        self, fn: Callable, args: tuple, kwargs: dict, timeout: Optional[float]
    ) -> Any:
        if timeout is None or timeout <= 0:
            return fn(*args, **kwargs)
        future = self._timeout_pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Job timed out after {timeout} seconds")

    def _execute_job(self, job: Job) -> None:
        with self._lock:
            self._active_workers += 1

        try:
            if job.status == JobStatus.CANCELLED:
                return

            job.status = JobStatus.RUNNING
            job.attempts += 1
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.RUNNING)
            self._fire_event("on_start", job)

            with self._lock:
                fn = self._handlers.get(job.fn_name)

            is_timeout = False
            exc: Optional[Exception] = None
            result: Any = None

            if fn is None:
                exc = KeyError(f"No handler registered for function: '{job.fn_name}'")
            else:
                try:
                    result = self._run_with_timeout(fn, job.args, job.kwargs, job.timeout)
                except TimeoutError as te:
                    is_timeout = True
                    exc = te
                except Exception as e:
                    exc = e

            if exc is None:
                if job.status == JobStatus.CANCELLED:
                    return
                job.status = JobStatus.COMPLETED
                job.result = result
                job.error = None
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
                self._fire_event("on_success", job)
                return

            # Handle execution failure
            if job.status == JobStatus.CANCELLED:
                return

            if is_timeout:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
                self._fire_event("on_failure", job)
            elif job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
                job.status = JobStatus.RETRYING
                delay = job.retry_policy.get_delay(job.attempts)
                job.scheduled_at = time.time() + delay
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.RETRYING)
                self.queue.push(job)
                self._fire_event("on_retry", job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
                self._fire_event("on_failure", job)

        finally:
            with self._lock:
                self._active_workers -= 1

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self.queue.pop(timeout=0.05)
            if job is None:
                continue
            if job.status == JobStatus.CANCELLED:
                continue
            self._execute_job(job)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            if self._timeout_pool._shutdown:
                self._timeout_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=max(self.num_workers * 4, 16)
                )
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-Worker-{i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        with self._lock:
            if not self._started:
                return
            self._stop_event.set()
            self._started = False

        if wait:
            end_time = time.time() + (timeout if timeout is not None else 5.0)
            for t in self._threads:
                rem = max(0.0, end_time - time.time())
                t.join(timeout=rem)
            try:
                self._timeout_pool.shutdown(wait=wait, cancel_futures=True)
            except Exception:
                pass
        else:
            try:
                self._timeout_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
