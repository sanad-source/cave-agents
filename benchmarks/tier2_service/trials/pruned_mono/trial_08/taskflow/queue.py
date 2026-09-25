"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from typing import Dict, List, Optional, Tuple

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    """Thread-safe priority queue with delayed scheduling and strict FIFO tie-breaking.

    Dequeue ordering:
    - Only jobs where scheduled_at <= time.time() are eligible.
    - Highest numerical priority dequeued first (CRITICAL(4) > HIGH(3) > MEDIUM(2) > LOW(1)).
    - For equal priority, earlier created_at / monotonic insertion counter dequeued first.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        # Heap elements: (-priority_int, created_at, counter, job_id, job)
        self._heap: List[Tuple[int, float, int, str, Job]] = []
        self._counter = itertools.count()
        # Mapping from job_id to the entry in _heap
        self._entry_finder: Dict[str, Tuple[int, float, int, str, Job]] = {}
        self._cancelled_ids: set[str] = set()

    def push(self, job: Job) -> None:
        """Push a job into the queue."""
        with self._lock:
            # If job was previously marked cancelled, clear it
            self._cancelled_ids.discard(job.job_id)
            priority_val = job.priority.value if isinstance(job.priority, JobPriority) else int(job.priority)
            count = next(self._counter)
            entry = (-priority_val, job.created_at, count, job.job_id, job)
            self._entry_finder[job.job_id] = entry
            heapq.heappush(self._heap, entry)
            self._not_empty.notify_all()

    def _purge_cancelled(self) -> None:
        """Remove cancelled entries from the top of the heap (caller holds lock)."""
        while self._heap and self._heap[0][3] in self._cancelled_ids:
            entry = heapq.heappop(self._heap)
            self._cancelled_ids.discard(entry[3])
            self._entry_finder.pop(entry[3], None)

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Blocks up to timeout seconds waiting for an eligible job.

        Returns None if timeout expires without available job.
        """
        deadline = (time.time() + timeout) if timeout is not None else None

        with self._lock:
            while True:
                self._purge_cancelled()

                now = time.time()
                # Check for eligible jobs
                # We need to find the highest-priority eligible job.
                # Notice: The heap is ordered by (-priority, created_at, count).
                # The top item might not be eligible yet (scheduled_at > now),
                # but another item might also not be eligible, or a lower priority item might be eligible!
                # Wait, does delayed scheduling mean that if a higher priority job is delayed,
                # can a lower priority job that is ready run, or does delayed scheduling apply across all jobs?
                # Usually in priority queues with delayed jobs:
                # Any job whose scheduled_at <= now is eligible.
                # Among all eligible jobs, the one with highest priority (and tie-breaking) runs.
                # Let's inspect all items or partition/filter them.
                eligible_idx = None
                earliest_future_scheduled: Optional[float] = None

                # Clean any cancelled entries lazily or compact heap if needed
                # Scan heap for eligible candidate
                for idx, entry in enumerate(self._heap):
                    _, _, _, j_id, candidate_job = entry
                    if j_id in self._cancelled_ids:
                        continue
                    if candidate_job.scheduled_at <= now:
                        # Since heap is a min-heap on (-priority, created_at, count),
                        # the first one encountered isn't guaranteed to be the overall best unless it's top.
                        # Wait! Let's find the best eligible entry among all heap items:
                        if eligible_idx is None:
                            eligible_idx = idx
                        else:
                            # Compare (-priority, created_at, count)
                            if self._heap[idx][:3] < self._heap[eligible_idx][:3]:
                                eligible_idx = idx
                    else:
                        if earliest_future_scheduled is None or candidate_job.scheduled_at < earliest_future_scheduled:
                            earliest_future_scheduled = candidate_job.scheduled_at

                if eligible_idx is not None:
                    # Pop the best eligible job
                    # If it's the root (idx == 0):
                    if eligible_idx == 0:
                        entry = heapq.heappop(self._heap)
                    else:
                        # Extract at eligible_idx and restore heap invariant
                        entry = self._heap[eligible_idx]
                        self._heap[eligible_idx] = self._heap[-1]
                        self._heap.pop()
                        heapq.heapify(self._heap)

                    _, _, _, j_id, job = entry
                    self._entry_finder.pop(j_id, None)
                    self._cancelled_ids.discard(j_id)
                    return job

                # No eligible job available right now.
                # If timeout is specified and expired:
                if deadline is not None and time.time() >= deadline:
                    return None

                # Calculate wait time: either until deadline, or until earliest_future_scheduled, whichever is earlier
                wait_time: Optional[float] = None
                now = time.time()
                if earliest_future_scheduled is not None:
                    delay_until_scheduled = max(0.001, earliest_future_scheduled - now)
                    if deadline is not None:
                        remaining = deadline - now
                        if remaining <= 0:
                            return None
                        wait_time = min(delay_until_scheduled, remaining)
                    else:
                        wait_time = delay_until_scheduled
                else:
                    if deadline is not None:
                        remaining = deadline - now
                        if remaining <= 0:
                            return None
                        wait_time = remaining
                    else:
                        wait_time = None

                # Wait on condition variable
                if wait_time is not None:
                    self._not_empty.wait(timeout=wait_time)
                else:
                    self._not_empty.wait()

    def peek(self) -> Optional[Job]:
        """Returns next eligible job without removing it, or None."""
        with self._lock:
            self._purge_cancelled()
            now = time.time()
            best_entry = None
            for entry in self._heap:
                _, _, _, j_id, job = entry
                if j_id in self._cancelled_ids:
                    continue
                if job.scheduled_at <= now:
                    if best_entry is None or entry[:3] < best_entry[:3]:
                        best_entry = entry
            return best_entry[4] if best_entry is not None else None

    def cancel(self, job_id: str) -> bool:
        """Marks job cancelled if in queue and removes it; returns True if found and removed."""
        with self._lock:
            if job_id in self._entry_finder and job_id not in self._cancelled_ids:
                self._cancelled_ids.add(job_id)
                self._entry_finder.pop(job_id, None)
                self._purge_cancelled()
                return True
            return False

    def size(self) -> int:
        """Current count of queued eligible and scheduled jobs (excluding cancelled)."""
        with self._lock:
            count = 0
            for entry in self._heap:
                if entry[3] not in self._cancelled_ids:
                    count += 1
            return count

    def is_empty(self) -> bool:
        """Returns True if there are no queued jobs, False otherwise."""
        return self.size() == 0
