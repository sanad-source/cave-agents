"""Thread-safe priority task queue with strict FIFO tie-breaking and delayed scheduling."""

import heapq
import itertools
import threading
import time
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._seq = itertools.count()
        # _ready_heap entries: (-priority_value, created_at, seq, job_id)
        self._ready_heap: list[tuple[int, float, int, str]] = []
        # _delayed_heap entries: (scheduled_at, -priority_value, created_at, seq, job_id)
        self._delayed_heap: list[tuple[float, int, float, int, str]] = []
        # job_id -> Job
        self._queued_jobs: dict[str, Job] = {}
        # job_id -> sequence number of latest push
        self._current_seq: dict[str, int] = {}
        # Set of cancelled job_ids
        self._cancelled_ids: set[str] = set()

    def _promote_delayed(self, now: float) -> None:
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            scheduled_at, neg_prio, created_at, seq, job_id = heapq.heappop(self._delayed_heap)
            if (
                job_id not in self._cancelled_ids
                and self._current_seq.get(job_id) == seq
                and job_id in self._queued_jobs
            ):
                heapq.heappush(self._ready_heap, (neg_prio, created_at, seq, job_id))

    def _clean_ready_heap(self) -> None:
        while self._ready_heap:
            _, _, seq, job_id = self._ready_heap[0]
            if (
                job_id in self._cancelled_ids
                or self._current_seq.get(job_id) != seq
                or job_id not in self._queued_jobs
            ):
                heapq.heappop(self._ready_heap)
            else:
                break

    def _clean_delayed_heap(self) -> None:
        while self._delayed_heap:
            _, _, _, seq, job_id = self._delayed_heap[0]
            if (
                job_id in self._cancelled_ids
                or self._current_seq.get(job_id) != seq
                or job_id not in self._queued_jobs
            ):
                heapq.heappop(self._delayed_heap)
            else:
                break

    def push(self, job: Job) -> None:
        with self._lock:
            now = time.time()
            seq = next(self._seq)
            self._queued_jobs[job.job_id] = job
            self._cancelled_ids.discard(job.job_id)
            self._current_seq[job.job_id] = seq

            prio_val = int(job.priority) if isinstance(job.priority, JobPriority) else int(job.priority)
            created_at = job.created_at if job.created_at is not None else now
            scheduled_at = job.scheduled_at if job.scheduled_at is not None else 0.0

            if scheduled_at > now:
                heapq.heappush(
                    self._delayed_heap,
                    (scheduled_at, -prio_val, created_at, seq, job.job_id),
                )
            else:
                heapq.heappush(
                    self._ready_heap,
                    (-prio_val, created_at, seq, job.job_id),
                )
            self._cv.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        deadline = (time.time() + timeout) if timeout is not None else None
        with self._lock:
            while True:
                now = time.time()
                self._promote_delayed(now)
                self._clean_ready_heap()

                if self._ready_heap:
                    _, _, seq, job_id = heapq.heappop(self._ready_heap)
                    job = self._queued_jobs.pop(job_id, None)
                    self._current_seq.pop(job_id, None)
                    if job is not None:
                        return job
                    continue

                if deadline is not None:
                    remaining = deadline - now
                    if remaining <= 0:
                        return None

                self._clean_delayed_heap()
                wait_time: Optional[float] = None
                if self._delayed_heap:
                    earliest_time = self._delayed_heap[0][0]
                    wait_time = max(0.0, earliest_time - now)

                if deadline is not None:
                    remaining = deadline - now
                    if wait_time is None or remaining < wait_time:
                        wait_time = remaining

                if wait_time is not None and wait_time <= 0:
                    continue

                self._cv.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        with self._lock:
            now = time.time()
            self._promote_delayed(now)
            self._clean_ready_heap()
            if self._ready_heap:
                job_id = self._ready_heap[0][3]
                return self._queued_jobs.get(job_id)
            return None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._queued_jobs:
                job = self._queued_jobs.pop(job_id)
                job.status = JobStatus.CANCELLED
                self._cancelled_ids.add(job_id)
                self._current_seq.pop(job_id, None)
                return True
            return False

    def size(self) -> int:
        with self._lock:
            return len(self._queued_jobs)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queued_jobs) == 0
