"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .models import Job, JobStatus


@dataclass(order=True)
class ReadyEntry:
    priority_score: int  # -job.priority.value
    created_at: float
    sequence: int
    job: Job = field(compare=False)


@dataclass(order=True)
class DelayedEntry:
    scheduled_at: float
    priority_score: int
    created_at: float
    sequence: int
    job: Job = field(compare=False)

    def to_ready_entry(self) -> ReadyEntry:
        return ReadyEntry(
            priority_score=self.priority_score,
            created_at=self.created_at,
            sequence=self.sequence,
            job=self.job,
        )


class PriorityTaskQueue:
    """Thread-safe priority queue with delayed job scheduling and FIFO tie-breaking."""

    def __init__(self):
        self._ready_queue: list[ReadyEntry] = []
        self._delayed_queue: list[DelayedEntry] = []
        self._cond = threading.Condition()
        self._seq = itertools.count()

    def push(self, job: Job) -> None:
        """Push a job into the queue."""
        with self._cond:
            seq = next(self._seq)
            now = time.time()
            if job.scheduled_at and job.scheduled_at > now:
                entry = DelayedEntry(
                    scheduled_at=job.scheduled_at,
                    priority_score=-job.priority.value,
                    created_at=job.created_at,
                    sequence=seq,
                    job=job,
                )
                heapq.heappush(self._delayed_queue, entry)
            else:
                entry = ReadyEntry(
                    priority_score=-job.priority.value,
                    created_at=job.created_at,
                    sequence=seq,
                    job=job,
                )
                heapq.heappush(self._ready_queue, entry)
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Pop the next eligible job, blocking up to timeout seconds.
        Returns None if timeout expires. Indefinite wait if timeout is None.
        """
        deadline = (time.time() + timeout) if timeout is not None else None

        with self._cond:
            while True:
                now = time.time()
                # Promote any delayed jobs that are now eligible
                while self._delayed_queue and self._delayed_queue[0].scheduled_at <= now:
                    delayed_item = heapq.heappop(self._delayed_queue)
                    heapq.heappush(self._ready_queue, delayed_item.to_ready_entry())

                if self._ready_queue:
                    entry = heapq.heappop(self._ready_queue)
                    return entry.job

                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    wait_time = remaining
                    if self._delayed_queue:
                        delay_time = self._delayed_queue[0].scheduled_at - time.time()
                        if delay_time <= 0:
                            continue
                        wait_time = min(wait_time, delay_time)
                    self._cond.wait(timeout=wait_time)
                else:
                    if self._delayed_queue:
                        delay_time = self._delayed_queue[0].scheduled_at - time.time()
                        if delay_time <= 0:
                            continue
                        self._cond.wait(timeout=delay_time)
                    else:
                        self._cond.wait()

    def peek(self) -> Optional[Job]:
        """Return the next eligible job without removing it, or None."""
        with self._cond:
            now = time.time()
            while self._delayed_queue and self._delayed_queue[0].scheduled_at <= now:
                delayed_item = heapq.heappop(self._delayed_queue)
                heapq.heappush(self._ready_queue, delayed_item.to_ready_entry())

            if self._ready_queue:
                return self._ready_queue[0].job
            return None

    def cancel(self, job_id: str) -> bool:
        """Marks job cancelled if in queue and removes it; returns True if found and removed."""
        with self._cond:
            for i, entry in enumerate(self._ready_queue):
                if entry.job.job_id == job_id:
                    self._ready_queue.pop(i)
                    heapq.heapify(self._ready_queue)
                    entry.job.status = JobStatus.CANCELLED
                    return True

            for i, d_entry in enumerate(self._delayed_queue):
                if d_entry.job.job_id == job_id:
                    self._delayed_queue.pop(i)
                    heapq.heapify(self._delayed_queue)
                    d_entry.job.status = JobStatus.CANCELLED
                    return True

            return False

    def size(self) -> int:
        """Current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._ready_queue) + len(self._delayed_queue)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        with self._cond:
            return len(self._ready_queue) == 0 and len(self._delayed_queue) == 0
