"""taskflow priority task queue with delayed scheduling and strict FIFO tie-breaking."""

import heapq
import threading
import time
from typing import Any, Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority queue with delayed execution and strict FIFO tie-breaking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._ready_heap: list[tuple[int, float, int, str, Job]] = []
        self._delayed_heap: list[tuple[float, int, float, int, str, Job]] = []
        self._counter: int = 0
        self._job_lookup: dict[str, Job] = {}
        self._job_entries: dict[str, set[int]] = {}

    def _transfer_ready_locked(self, now: float) -> None:
        """Move jobs whose scheduled_at <= now from delayed heap to ready heap."""
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            sched, neg_p, c_at, cnt, j_id, job = heapq.heappop(self._delayed_heap)
            counts = self._job_entries.get(j_id)
            if counts is not None and cnt in counts:
                heapq.heappush(self._ready_heap, (neg_p, c_at, cnt, j_id, job))

    def push(self, job: Job) -> None:
        """Push a job into the queue, either to ready heap or delayed heap based on scheduled_at."""
        with self._cond:
            now = time.time()
            self._counter += 1
            count = self._counter
            self._job_lookup[job.job_id] = job
            if job.job_id not in self._job_entries:
                self._job_entries[job.job_id] = set()
            self._job_entries[job.job_id].add(count)

            prio_val = int(
                job.priority.value
                if isinstance(job.priority, JobPriority)
                else job.priority
            )

            if job.scheduled_at and job.scheduled_at > now:
                heapq.heappush(
                    self._delayed_heap,
                    (job.scheduled_at, -prio_val, job.created_at, count, job.job_id, job),
                )
            else:
                heapq.heappush(
                    self._ready_heap,
                    (-prio_val, job.created_at, count, job.job_id, job),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Pop the highest priority eligible job. Blocks up to timeout seconds.
        
        Returns None if timeout expires without an eligible job.
        """
        with self._cond:
            deadline = (time.time() + timeout) if timeout is not None else None

            while True:
                now = time.time()
                self._transfer_ready_locked(now)

                # Check ready heap for a valid job
                while self._ready_heap:
                    neg_p, c_at, cnt, j_id, job = heapq.heappop(self._ready_heap)
                    counts = self._job_entries.get(j_id)
                    if counts is not None and cnt in counts:
                        counts.remove(cnt)
                        if not counts:
                            self._job_entries.pop(j_id, None)
                            self._job_lookup.pop(j_id, None)
                        return job

                # Prune stale cancelled jobs from top of delayed heap
                while self._delayed_heap:
                    sched, neg_p, c_at, cnt, j_id, _ = self._delayed_heap[0]
                    counts = self._job_entries.get(j_id)
                    if counts is not None and cnt in counts:
                        break
                    heapq.heappop(self._delayed_heap)

                # Determine wait timeout
                time_to_deadline: Optional[float] = None
                if deadline is not None:
                    time_to_deadline = deadline - now
                    if time_to_deadline <= 0:
                        return None

                time_to_delayed: Optional[float] = None
                if self._delayed_heap:
                    earliest_sched = self._delayed_heap[0][0]
                    time_to_delayed = max(0.0, earliest_sched - now)

                sleep_duration: Optional[float] = None
                if time_to_deadline is not None and time_to_delayed is not None:
                    sleep_duration = min(time_to_deadline, time_to_delayed)
                elif time_to_deadline is not None:
                    sleep_duration = time_to_deadline
                elif time_to_delayed is not None:
                    sleep_duration = time_to_delayed

                if sleep_duration is not None and sleep_duration <= 0:
                    continue

                if not self._cond.wait(timeout=sleep_duration):
                    # Timeout elapsed during wait
                    if deadline is not None and time.time() >= deadline:
                        # Double-check if any job matured right at deadline
                        now = time.time()
                        self._transfer_ready_locked(now)
                        while self._ready_heap:
                            neg_p, c_at, cnt, j_id, job = heapq.heappop(self._ready_heap)
                            counts = self._job_entries.get(j_id)
                            if counts is not None and cnt in counts:
                                counts.remove(cnt)
                                if not counts:
                                    self._job_entries.pop(j_id, None)
                                    self._job_lookup.pop(j_id, None)
                                return job
                        return None

    def peek(self) -> Optional[Job]:
        """Return the next eligible job without removing it, or None."""
        with self._cond:
            now = time.time()
            self._transfer_ready_locked(now)
            while self._ready_heap:
                neg_p, c_at, cnt, j_id, job = self._ready_heap[0]
                counts = self._job_entries.get(j_id)
                if counts is not None and cnt in counts:
                    return job
                heapq.heappop(self._ready_heap)
            return None

    def cancel(self, job_id: str) -> bool:
        """Mark job cancelled if in queue and remove it. Returns True if found and cancelled."""
        with self._cond:
            if job_id in self._job_lookup:
                job = self._job_lookup.pop(job_id)
                self._job_entries.pop(job_id, None)
                job.status = JobStatus.CANCELLED
                self._cond.notify_all()
                return True
            return False

    def size(self) -> int:
        """Current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._job_lookup)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        with self._cond:
            return len(self._job_lookup) == 0
