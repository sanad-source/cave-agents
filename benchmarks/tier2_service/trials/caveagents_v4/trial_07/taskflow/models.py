"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

import enum
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


class JobPriority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.05
    backoff_factor: float = 2.0
    jitter: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (self.backoff_factor ** max(0, attempt - 1))
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay


@dataclass
class Job:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fn_name: str = ""
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: JobPriority = JobPriority.MEDIUM
    status: JobStatus = JobStatus.PENDING
    retry_policy: Optional[RetryPolicy] = None
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    scheduled_at: float = 0.0
    timeout: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = str(uuid.uuid4())

        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        elif isinstance(self.priority, str):
            try:
                self.priority = JobPriority[self.priority]
            except KeyError:
                self.priority = JobPriority(int(self.priority))

        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            try:
                self.status = JobStatus(self.status)
            except ValueError:
                self.status = JobStatus[self.status]

        if not isinstance(self.args, tuple):
            self.args = tuple(self.args)
        if self.kwargs is None:
            self.kwargs = {}
        elif not isinstance(self.kwargs, dict):
            self.kwargs = dict(self.kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if isinstance(self.priority, JobPriority) else int(self.priority),
            "status": self.status.value if isinstance(self.status, JobStatus) else str(self.status),
            "retry_policy": asdict(self.retry_policy) if self.retry_policy is not None else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        priority_val = data.get("priority", JobPriority.MEDIUM)
        if isinstance(priority_val, str):
            try:
                priority = JobPriority[priority_val]
            except KeyError:
                priority = JobPriority(int(priority_val))
        elif isinstance(priority_val, int) and not isinstance(priority_val, JobPriority):
            priority = JobPriority(priority_val)
        else:
            priority = priority_val

        status_val = data.get("status", JobStatus.PENDING)
        if isinstance(status_val, str) and not isinstance(status_val, JobStatus):
            try:
                status = JobStatus(status_val)
            except ValueError:
                status = JobStatus[status_val]
        else:
            status = status_val

        rp_data = data.get("retry_policy")
        retry_policy = None
        if rp_data is not None:
            if isinstance(rp_data, RetryPolicy):
                retry_policy = rp_data
            elif isinstance(rp_data, dict):
                retry_policy = RetryPolicy(**rp_data)

        created_at = data.get("created_at")
        if created_at is None:
            created_at = time.time()

        return cls(
            job_id=data.get("job_id") or str(uuid.uuid4()),
            fn_name=data.get("fn_name", ""),
            args=tuple(data.get("args", ())),
            kwargs=dict(data.get("kwargs", {})),
            priority=priority,
            status=status,
            retry_policy=retry_policy,
            attempts=data.get("attempts", 0),
            result=data.get("result"),
            error=data.get("error"),
            created_at=created_at,
            scheduled_at=float(data.get("scheduled_at", 0.0)),
            timeout=data.get("timeout"),
        )
