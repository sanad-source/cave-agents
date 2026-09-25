"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from taskflow.models import Job, JobPriority, JobStatus


@dataclass(order=True)
class ReadyEntry:
    """Entry stored in the ready min-heap."""
    priority_neg: int
    created_at: float
    seq: int
    job: Any = field(compare=False)


@dataclass(order=True)
class DelayedEntry:
    """Entry stored in the delayed min-heap."""
    scheduled_at: float
    priority_neg: int
    created_at: float
    seq: int
    job: Any = field(compare=False)


class PriorityTaskQueue:
    """Thread-safe priority queue backed by min-heap with strict FIFO tie-breaking and delayed scheduling."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._ready_queue: List[ReadyEntry] = []
        self._delayed_queue: List[DelayedEntry] = []
        self._job_ids: Dict[str, Job] = {}
        self._seq = itertools.count()

    def _transfer_delayed(self) -> None:
        """Transfers all delayed jobs whose scheduled_at has arrived into ready_queue."""
        now = time.time()
        while self._delayed_queue and self._delayed_queue[0].scheduled_at <= now:
            delayed = heapq.heappop(self._delayed_queue)
            ready = ReadyEntry(
                priority_neg=delayed.priority_neg,
                created_at=delayed.created_at,
                seq=delayed.seq,
                job=delayed.job,
            )
            heapq.heappush(self._ready_queue, ready)

    def push(self, job: Job) -> None:
        """Pushes a job into the queue, either into ready or delayed pool based on scheduled_at."""
        with self._cond:
            # If job is already in queue, remove previous instance
            if job.job_id in self._job_ids:
                self._ready_queue = [e for e in self._ready_queue if e.job.job_id != job.job_id]
                heapq.heapify(self._ready_queue)
                self._delayed_queue = [e for e in self._delayed_queue if e.job.job_id != job.job_id]
                heapq.heapify(self._delayed_queue)

            seq = next(self._seq)
            p_val = int(job.priority) if isinstance(job.priority, (JobPriority, int)) else 2
            p_neg = -p_val
            created_at = float(job.created_at if job.created_at is not None else time.time())
            scheduled_at = float(job.scheduled_at if job.scheduled_at is not None else 0.0)

            now = time.time()
            if scheduled_at > now:
                heapq.heappush(
                    self._delayed_queue,
                    DelayedEntry(
                        scheduled_at=scheduled_at,
                        priority_neg=p_neg,
                        created_at=created_at,
                        seq=seq,
                        job=job,
                    ),
                )
            else:
                heapq.heappush(
                    self._ready_queue,
                    ReadyEntry(
                        priority_neg=p_neg,
                        created_at=created_at,
                        seq=seq,
                        job=job,
                    ),
                )

            self._job_ids[job.job_id] = job
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Blocks up to timeout seconds waiting for an eligible job. Returns None if timeout expires."""
        with self._cond:
            deadline = None if timeout is None else time.time() + max(0.0, timeout)

            while True:
                self._transfer_delayed()

                if self._ready_queue:
                    entry = heapq.heappop(self._ready_queue)
                    self._job_ids.pop(entry.job.job_id, None)
                    return entry.job

                now = time.time()
                if deadline is not None:
                    remaining = deadline - now
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                # Calculate wait duration until next delayed job or deadline
                wait_time = remaining
                if self._delayed_queue:
                    time_until_delayed = max(0.0, self._delayed_queue[0].scheduled_at - now)
                    if wait_time is None or time_until_delayed < wait_time:
                        wait_time = time_until_delayed

                if wait_time is not None and wait_time <= 0:
                    continue

                self._cond.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        """Returns the next eligible job without removing it, or None."""
        with self._cond:
            self._transfer_delayed()
            if self._ready_queue:
                return self._ready_queue[0].job
            return None

    def cancel(self, job_id: str) -> bool:
        """Marks job cancelled if in queue and removes it; returns True if found and removed."""
        with self._cond:
            if job_id not in self._job_ids:
                return False

            job = self._job_ids.pop(job_id)
            job.status = JobStatus.CANCELLED

            self._ready_queue = [e for e in self._ready_queue if e.job.job_id != job_id]
            heapq.heapify(self._ready_queue)

            self._delayed_queue = [e for e in self._delayed_queue if e.job.job_id != job_id]
            heapq.heapify(self._delayed_queue)

            self._cond.notify_all()
            return True

    def size(self) -> int:
        """Current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._job_ids)

    def is_empty(self) -> bool:
        """Returns True if no jobs are in the queue, False otherwise."""
        with self._cond:
            return len(self._job_ids) == 0
