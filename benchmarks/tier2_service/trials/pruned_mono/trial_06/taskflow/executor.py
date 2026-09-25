import threading
import time
from typing import Any, Callable, Optional, Union

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    def __init__(
        self,
        queue: Optional[Union[PriorityTaskQueue, int]] = None,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        if isinstance(queue, int):
            num_workers = queue
            queue = None

        self.queue: PriorityTaskQueue = (
            queue if isinstance(queue, PriorityTaskQueue) else PriorityTaskQueue()
        )
        self.num_workers: int = num_workers
        self.storage: Optional[JobStorage] = storage

        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._running: bool = False
        self._active_workers: int = 0

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

    def _trigger_listeners(self, event: str, job: Job) -> None:
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
            self._stop_event.clear()
            self._running = True
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
        self._stop_event.set()
        if wait:
            start_time = time.monotonic()
            for thread in self._threads:
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        break
                    thread.join(timeout=max(0.0, remaining))
                else:
                    thread.join()
        with self._lock:
            self._threads.clear()
            self._running = False

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self.queue.pop(timeout=0.1)
            if job is None:
                continue

            with self._lock:
                self._active_workers += 1
            try:
                self._execute_job(job)
            finally:
                with self._lock:
                    self._active_workers -= 1

    def _execute_job(self, job: Job) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self.storage:
            self.storage.update_status(job.job_id, JobStatus.RUNNING)
        self._trigger_listeners("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            self._handle_failure(
                job,
                KeyError(f"No handler registered for function '{job.fn_name}'"),
                is_timeout=False,
            )
            return

        try:
            if job.timeout is not None:
                result = self._run_with_timeout(handler, job.args, job.kwargs, job.timeout)
            else:
                result = handler(*job.args, **job.kwargs)
        except TimeoutError as te:
            self._handle_failure(job, te, is_timeout=True)
        except Exception as exc:
            self._handle_failure(job, exc, is_timeout=False)
        else:
            if job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.COMPLETED
            job.result = result
            job.error = None
            if self.storage:
                self.storage.update_status(
                    job.job_id, JobStatus.COMPLETED, result=result, error=None
                )
            self._trigger_listeners("on_success", job)

    def _run_with_timeout(
        self,
        handler: Callable,
        args: tuple,
        kwargs: dict,
        timeout: float,
    ) -> Any:
        result = [None]
        exc = [None]
        done = threading.Event()

        def target():
            try:
                result[0] = handler(*args, **kwargs)
            except Exception as e:
                exc[0] = e
            finally:
                done.set()

        t = threading.Thread(target=target, daemon=True)
        t.start()
        if not done.wait(timeout=max(0.0, timeout)):
            raise TimeoutError(f"Job execution timed out after {timeout} seconds")
        if exc[0] is not None:
            raise exc[0]
        return result[0]

    def _handle_failure(self, job: Job, exc: Exception, is_timeout: bool = False) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        error_msg = str(exc) if str(exc) else repr(exc)
        job.error = error_msg

        if is_timeout:
            job.status = JobStatus.FAILED
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=error_msg)
            self._trigger_listeners("on_failure", job)
        elif job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
            job.status = JobStatus.RETRYING
            delay = job.retry_policy.get_delay(job.attempts)
            job.scheduled_at = time.time() + delay
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.RETRYING, error=error_msg)
            self.queue.push(job)
            self._trigger_listeners("on_retry", job)
        else:
            job.status = JobStatus.FAILED
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=error_msg)
            self._trigger_listeners("on_failure", job)
