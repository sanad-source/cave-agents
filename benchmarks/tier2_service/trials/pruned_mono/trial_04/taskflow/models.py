"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any, Optional


class JobPriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(str, Enum):
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
    args: tuple = field(default_factory=tuple)
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
        if isinstance(self.args, list):
            self.args = tuple(self.args)
        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if hasattr(self.priority, "value") else int(self.priority),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "retry_policy": asdict(self.retry_policy) if self.retry_policy is not None else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        rp_data = data.get("retry_policy")
        retry_policy = RetryPolicy(**rp_data) if rp_data is not None else None

        priority_val = data.get("priority", JobPriority.MEDIUM.value)
        if isinstance(priority_val, int):
            priority = JobPriority(priority_val)
        else:
            priority = priority_val

        status_val = data.get("status", JobStatus.PENDING.value)
        if isinstance(status_val, str):
            status = JobStatus(status_val)
        else:
            status = status_val

        return cls(
            job_id=data["job_id"],
            fn_name=data.get("fn_name", ""),
            args=tuple(data.get("args", ())),
            kwargs=dict(data.get("kwargs", {})),
            priority=priority,
            status=status,
            retry_policy=retry_policy,
            attempts=data.get("attempts", 0),
            result=data.get("result", None),
            error=data.get("error", None),
            created_at=data.get("created_at", time.time()),
            scheduled_at=data.get("scheduled_at", 0.0),
            timeout=data.get("timeout", None),
        )
