"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import threading
import time
from typing import Any, Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority task queue backing taskflow.

    - Higher numerical priority dequeued first (CRITICAL > HIGH > MEDIUM > LOW).
    - Equal priority tie-broken by earlier created_at / monotonic insertion order.
    - Delayed jobs (scheduled_at > time.time()) only become eligible when time.time() >= scheduled_at.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        # Heap entry for ready jobs: (-prio_val, created_at, seq, job)
        self._ready_heap: list[tuple[int, float, int, Job]] = []
        # Heap entry for delayed jobs: (scheduled_at, -prio_val, created_at, seq, job)
        self._delayed_heap: list[tuple[float, int, float, int, Job]] = []
        self._seq: int = 0

    def _transfer_delayed(self, now: float) -> None:
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            _, neg_prio, created_at, seq, job = heapq.heappop(self._delayed_heap)
            heapq.heappush(self._ready_heap, (neg_prio, created_at, seq, job))

    def push(self, job: Job) -> None:
        with self._cond:
            self._seq += 1
            now = time.time()
            prio_val = job.priority.value if isinstance(job.priority, JobPriority) else int(job.priority)
            if job.scheduled_at > now:
                heapq.heappush(
                    self._delayed_heap,
                    (job.scheduled_at, -prio_val, job.created_at, self._seq, job),
                )
            else:
                heapq.heappush(
                    self._ready_heap,
                    (-prio_val, job.created_at, self._seq, job),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        with self._cond:
            start_time = time.time()
            while True:
                now = time.time()
                self._transfer_delayed(now)
                if self._ready_heap:
                    _, _, _, job = heapq.heappop(self._ready_heap)
                    return job

                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None

                    if self._delayed_heap:
                        earliest_scheduled = self._delayed_heap[0][0]
                        time_to_wait = earliest_scheduled - time.time()
                        if time_to_wait <= 0:
                            continue
                        wait_time = min(remaining, time_to_wait)
                    else:
                        wait_time = remaining

                    self._cond.wait(timeout=wait_time)
                else:
                    if self._delayed_heap:
                        earliest_scheduled = self._delayed_heap[0][0]
                        time_to_wait = earliest_scheduled - time.time()
                        if time_to_wait <= 0:
                            continue
                        self._cond.wait(timeout=time_to_wait)
                    else:
                        self._cond.wait()

    def peek(self) -> Optional[Job]:
        """Returns next eligible job without removing it, or None."""
        with self._cond:
            now = time.time()
            self._transfer_delayed(now)
            if self._ready_heap:
                return self._ready_heap[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        """Marks job cancelled if in queue and removes it; returns True if found and removed."""
        with self._cond:
            # Check ready heap
            for i, item in enumerate(self._ready_heap):
                if item[3].job_id == job_id:
                    job = item[3]
                    job.status = JobStatus.CANCELLED
                    self._ready_heap.pop(i)
                    heapq.heapify(self._ready_heap)
                    return True

            # Check delayed heap
            for i, item in enumerate(self._delayed_heap):
                if item[4].job_id == job_id:
                    job = item[4]
                    job.status = JobStatus.CANCELLED
                    self._delayed_heap.pop(i)
                    heapq.heapify(self._delayed_heap)
                    return True

            return False

    def size(self) -> int:
        """Current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._ready_heap) + len(self._delayed_heap)

    def is_empty(self) -> bool:
        with self._cond:
            return (len(self._ready_heap) + len(self._delayed_heap)) == 0
