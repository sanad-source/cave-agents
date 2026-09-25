"""taskflow.queue: Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

import heapq
import threading
import time
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        # Heap elements for ready jobs: (-priority, created_at, counter, job)
        self._ready_heap: list[tuple] = []
        # Heap elements for scheduled jobs: (scheduled_at, -priority, created_at, counter, job)
        self._scheduled_heap: list[tuple] = []
        self._jobs: dict[str, Job] = {}
        self._counter: int = 0
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)

    def _transfer_scheduled(self) -> None:
        now = time.time()
        while self._scheduled_heap and self._scheduled_heap[0][0] <= now:
            _, neg_prio, created_at, counter, job = heapq.heappop(self._scheduled_heap)
            heapq.heappush(self._ready_heap, (neg_prio, created_at, counter, job))

    def push(self, job: Job) -> None:
        with self._condition:
            if job.job_id in self._jobs:
                self._ready_heap = [e for e in self._ready_heap if e[3].job_id != job.job_id]
                heapq.heapify(self._ready_heap)
                self._scheduled_heap = [e for e in self._scheduled_heap if e[4].job_id != job.job_id]
                heapq.heapify(self._scheduled_heap)

            self._counter += 1
            self._jobs[job.job_id] = job
            now = time.time()
            priority_val = int(job.priority) if job.priority is not None else int(JobPriority.MEDIUM)
            created_at = float(job.created_at) if job.created_at is not None else 0.0

            if job.scheduled_at and job.scheduled_at > now:
                heapq.heappush(
                    self._scheduled_heap,
                    (float(job.scheduled_at), -priority_val, created_at, self._counter, job),
                )
            else:
                heapq.heappush(
                    self._ready_heap,
                    (-priority_val, created_at, self._counter, job),
                )
            self._condition.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        start_time = time.time()
        with self._condition:
            while True:
                self._transfer_scheduled()
                if self._ready_heap:
                    _, _, _, job = heapq.heappop(self._ready_heap)
                    self._jobs.pop(job.job_id, None)
                    return job

                now = time.time()
                if timeout is not None:
                    elapsed = now - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                wait_time = remaining
                if self._scheduled_heap:
                    delay_needed = max(0.0, self._scheduled_heap[0][0] - now)
                    if wait_time is None:
                        wait_time = delay_needed
                    else:
                        wait_time = min(wait_time, delay_needed)

                if wait_time is not None:
                    if wait_time <= 0:
                        continue
                    self._condition.wait(timeout=wait_time)
                else:
                    self._condition.wait()

    def peek(self) -> Optional[Job]:
        with self._condition:
            self._transfer_scheduled()
            if self._ready_heap:
                return self._ready_heap[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            if job_id not in self._jobs:
                return False
            job = self._jobs.pop(job_id)
            job.status = JobStatus.CANCELLED
            self._ready_heap = [e for e in self._ready_heap if e[3].job_id != job_id]
            heapq.heapify(self._ready_heap)
            self._scheduled_heap = [e for e in self._scheduled_heap if e[4].job_id != job_id]
            heapq.heapify(self._scheduled_heap)
            return True

    def size(self) -> int:
        with self._condition:
            return len(self._jobs)

    def is_empty(self) -> bool:
        with self._condition:
            return len(self._jobs) == 0
