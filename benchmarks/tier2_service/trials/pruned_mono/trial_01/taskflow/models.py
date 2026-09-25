"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
import enum
import random
import time
from typing import Any, Optional
import uuid


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
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        return cls(**data)


@dataclass
class Job:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fn_name: str = ""
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
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
        if not isinstance(self.args, tuple):
            self.args = tuple(self.args)
        if not isinstance(self.kwargs, dict):
            self.kwargs = dict(self.kwargs)
        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)
        if isinstance(self.retry_policy, dict):
            self.retry_policy = RetryPolicy.from_dict(self.retry_policy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if isinstance(self.priority, JobPriority) else int(self.priority),
            "status": self.status.value if isinstance(self.status, JobStatus) else str(self.status),
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy is not None else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        d = dict(data)
        if "priority" in d and not isinstance(d["priority"], JobPriority):
            d["priority"] = JobPriority(d["priority"])
        if "status" in d and not isinstance(d["status"], JobStatus):
            d["status"] = JobStatus(d["status"])
        if d.get("retry_policy") is not None and not isinstance(d["retry_policy"], RetryPolicy):
            d["retry_policy"] = RetryPolicy.from_dict(d["retry_policy"])
        if "args" in d:
            d["args"] = tuple(d["args"])
        return cls(**d)
