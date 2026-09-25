"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import threading
import time
from typing import Optional

from taskflow.models import Job, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority task queue with delayed scheduling and strict FIFO tie-breaking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        # Ready heap items: (-priority_value, created_at, seq, job)
        self._ready: list[tuple[int, float, int, Job]] = []
        # Delayed heap items: (scheduled_at, -priority_value, created_at, seq, job)
        self._delayed: list[tuple[float, int, float, int, Job]] = []
        self._seq = 0

    def _move_delayed_to_ready(self, now: float) -> None:
        while self._delayed and self._delayed[0][0] <= now:
            _, neg_prio, created_at, seq, job = heapq.heappop(self._delayed)
            heapq.heappush(self._ready, (neg_prio, created_at, seq, job))

    def push(self, job: Job) -> None:
        """Push a job into the queue. If scheduled_at is in the future, delays eligibility."""
        with self._lock:
            self._seq += 1
            now = time.time()
            if job.scheduled_at > now:
                heapq.heappush(
                    self._delayed,
                    (job.scheduled_at, -job.priority.value, job.created_at, self._seq, job),
                )
            else:
                heapq.heappush(
                    self._ready,
                    (-job.priority.value, job.created_at, self._seq, job),
                )
            self._cv.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Block up to timeout seconds waiting for an eligible job. Returns None if timed out."""
        deadline = None if timeout is None else time.time() + max(0.0, timeout)
        with self._lock:
            while True:
                now = time.time()
                self._move_delayed_to_ready(now)
                if self._ready:
                    _, _, _, job = heapq.heappop(self._ready)
                    return job

                if timeout is not None:
                    remaining = deadline - now
                    if remaining <= 0:
                        return None
                    if self._delayed:
                        wait_time = min(remaining, max(0.0, self._delayed[0][0] - now))
                    else:
                        wait_time = remaining
                    self._cv.wait(wait_time)
                else:
                    if self._delayed:
                        wait_time = max(0.0, self._delayed[0][0] - now)
                        self._cv.wait(wait_time)
                    else:
                        self._cv.wait()

    def peek(self) -> Optional[Job]:
        """Return the next eligible job without removing it, or None if none eligible."""
        with self._lock:
            self._move_delayed_to_ready(time.time())
            if self._ready:
                return self._ready[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        """Mark job cancelled if in queue and remove it. Return True if found and removed."""
        with self._lock:
            for i, item in enumerate(self._ready):
                job = item[3]
                if job.job_id == job_id:
                    job.status = JobStatus.CANCELLED
                    self._ready.pop(i)
                    heapq.heapify(self._ready)
                    return True

            for i, d_item in enumerate(self._delayed):
                job = d_item[4]
                if job.job_id == job_id:
                    job.status = JobStatus.CANCELLED
                    self._delayed.pop(i)
                    heapq.heapify(self._delayed)
                    return True

            return False

    def size(self) -> int:
        """Return current count of queued eligible and scheduled jobs."""
        with self._lock:
            return len(self._ready) + len(self._delayed)

    def is_empty(self) -> bool:
        """Return True if both ready and delayed queues are empty."""
        with self._lock:
            return len(self._ready) == 0 and len(self._delayed) == 0
