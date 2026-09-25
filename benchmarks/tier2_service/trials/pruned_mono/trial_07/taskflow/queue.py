"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

import heapq
import itertools
import threading
import time
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority task queue backed by a min-heap with strict FIFO tie-breaking

    and delayed scheduling support.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._counter = itertools.count()

        # Elements in _ready_heap: (-priority_value, created_at, seq, job_id)
        self._ready_heap: list[tuple[int, float, int, str]] = []

        # Elements in _delayed_heap: (scheduled_at, -priority_value, created_at, seq, job_id)
        self._delayed_heap: list[tuple[float, int, float, int, str]] = []

        # job_id -> Job mapping of active jobs currently held in the queue
        self._jobs_by_id: dict[str, Job] = {}

    def _transfer_delayed(self, now: float) -> None:
        """Transfer jobs whose scheduled_at has arrived from delayed_heap to ready_heap."""
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            sched, neg_prio, created_at, seq, jid = heapq.heappop(self._delayed_heap)
            if jid in self._jobs_by_id:
                heapq.heappush(self._ready_heap, (neg_prio, created_at, seq, jid))

    def _clean_stale_delayed(self) -> None:
        """Discard cancelled or removed jobs from the top of delayed_heap."""
        while self._delayed_heap and self._delayed_heap[0][4] not in self._jobs_by_id:
            heapq.heappop(self._delayed_heap)

    def _clean_stale_ready(self) -> None:
        """Discard cancelled or removed jobs from the top of ready_heap."""
        while self._ready_heap and self._ready_heap[0][3] not in self._jobs_by_id:
            heapq.heappop(self._ready_heap)

    def push(self, job: Job) -> None:
        """Push a job into the queue, accounting for priority and delayed scheduling."""
        with self._cond:
            seq = next(self._counter)
            self._jobs_by_id[job.job_id] = job
            now = time.time()

            prio_val = int(job.priority.value if hasattr(job.priority, "value") else job.priority)
            neg_prio = -prio_val
            created_at = job.created_at

            if job.scheduled_at and job.scheduled_at > now:
                heapq.heappush(self._delayed_heap, (job.scheduled_at, neg_prio, created_at, seq, job.job_id))
            else:
                heapq.heappush(self._ready_heap, (neg_prio, created_at, seq, job.job_id))
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Pop the highest priority eligible job, blocking up to timeout seconds.

        Returns None if timeout expires without an eligible job.
        """
        deadline = (time.time() + timeout) if timeout is not None else None
        with self._cond:
            while True:
                now = time.time()
                self._transfer_delayed(now)
                self._clean_stale_ready()

                if self._ready_heap:
                    _, _, _, jid = heapq.heappop(self._ready_heap)
                    if jid in self._jobs_by_id:
                        return self._jobs_by_id.pop(jid)

                if deadline is not None and now >= deadline:
                    return None

                self._clean_stale_delayed()
                wait_time: Optional[float] = None
                if self._delayed_heap:
                    earliest_sched = self._delayed_heap[0][0]
                    wait_time = max(0.0, earliest_sched - now)
                    if wait_time <= 0.0:
                        continue

                if deadline is not None:
                    remaining = max(0.0, deadline - now)
                    if remaining <= 0.0:
                        return None
                    if wait_time is None or remaining < wait_time:
                        wait_time = remaining

                self._cond.wait(wait_time)

    def peek(self) -> Optional[Job]:
        """Return the next eligible job without removing it, or None if none eligible."""
        with self._cond:
            now = time.time()
            self._transfer_delayed(now)
            self._clean_stale_ready()
            if self._ready_heap:
                jid = self._ready_heap[0][3]
                return self._jobs_by_id.get(jid)
            return None

    def cancel(self, job_id: str) -> bool:
        """Mark job cancelled if in queue and remove it. Returns True if found and removed."""
        with self._cond:
            if job_id in self._jobs_by_id:
                job = self._jobs_by_id.pop(job_id)
                job.status = JobStatus.CANCELLED
                self._clean_stale_ready()
                self._clean_stale_delayed()
                self._cond.notify_all()
                return True
            return False

    def size(self) -> int:
        """Return current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._jobs_by_id)

    def is_empty(self) -> bool:
        """Return True if no jobs are in the queue."""
        with self._cond:
            return len(self._jobs_by_id) == 0
