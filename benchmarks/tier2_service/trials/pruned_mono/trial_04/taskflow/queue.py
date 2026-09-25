"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from typing import Optional

from taskflow.models import Job, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority queue with delayed job scheduling support."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        # Heap items: (-priority_value, created_at, sequence_id, job)
        self._ready_queue: list[tuple[int, float, int, Job]] = []
        # Heap items: (scheduled_at, -priority_value, created_at, sequence_id, job)
        self._delayed_queue: list[tuple[float, int, float, int, Job]] = []
        self._seq = itertools.count()

    def _transfer_delayed(self) -> None:
        """Move eligible delayed jobs to the ready queue."""
        now = time.time()
        while self._delayed_queue and self._delayed_queue[0][0] <= now:
            _, neg_prio, created_at, seq, job = heapq.heappop(self._delayed_queue)
            heapq.heappush(self._ready_queue, (neg_prio, created_at, seq, job))

    def push(self, job: Job) -> None:
        """Push a job into the queue."""
        with self._lock:
            seq = next(self._seq)
            prio_val = int(job.priority.value if hasattr(job.priority, "value") else job.priority)
            neg_prio = -prio_val
            created_at = float(job.created_at)
            now = time.time()

            if job.scheduled_at > now:
                heapq.heappush(
                    self._delayed_queue,
                    (float(job.scheduled_at), neg_prio, created_at, seq, job),
                )
            else:
                heapq.heappush(
                    self._ready_queue,
                    (neg_prio, created_at, seq, job),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Pop the highest priority ready job. Blocks up to timeout seconds."""
        with self._lock:
            deadline = (time.time() + timeout) if timeout is not None else None
            while True:
                self._transfer_delayed()
                if self._ready_queue:
                    _, _, _, job = heapq.heappop(self._ready_queue)
                    return job

                now = time.time()
                if deadline is not None:
                    remaining = deadline - now
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                if self._delayed_queue:
                    earliest_delayed = self._delayed_queue[0][0]
                    delay = max(0.0, earliest_delayed - now)
                    wait_time = min(remaining, delay) if remaining is not None else delay
                    self._cond.wait(wait_time)
                else:
                    if remaining is not None:
                        self._cond.wait(remaining)
                    else:
                        self._cond.wait()

    def peek(self) -> Optional[Job]:
        """Return next eligible job without removing it, or None."""
        with self._lock:
            self._transfer_delayed()
            if not self._ready_queue:
                return None
            return self._ready_queue[0][3]

    def cancel(self, job_id: str) -> bool:
        """Cancel and remove job from queue if present."""
        with self._lock:
            for i, item in enumerate(self._ready_queue):
                if item[3].job_id == job_id:
                    job = item[3]
                    self._ready_queue.pop(i)
                    heapq.heapify(self._ready_queue)
                    job.status = JobStatus.CANCELLED
                    return True
            for i, item in enumerate(self._delayed_queue):
                if item[4].job_id == job_id:
                    job = item[4]
                    self._delayed_queue.pop(i)
                    heapq.heapify(self._delayed_queue)
                    job.status = JobStatus.CANCELLED
                    return True
            return False

    def size(self) -> int:
        """Return total count of queued eligible and delayed jobs."""
        with self._lock:
            return len(self._ready_queue) + len(self._delayed_queue)

    def is_empty(self) -> bool:
        """Return True if no jobs are in queue."""
        with self._lock:
            return (len(self._ready_queue) + len(self._delayed_queue)) == 0
