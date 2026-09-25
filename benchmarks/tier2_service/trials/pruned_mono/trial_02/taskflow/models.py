"""Data models, enums, retry policies, and serialization for taskflow."""

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
            delay += random.uniform(0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryPolicy":
        return cls(
            max_attempts=data.get("max_attempts", 3),
            base_delay=data.get("base_delay", 0.05),
            backoff_factor=data.get("backoff_factor", 2.0),
            jitter=data.get("jitter", False),
        )


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
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)
        if isinstance(self.args, list):
            self.args = tuple(self.args)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": self.kwargs,
            "priority": self.priority.value if isinstance(self.priority, JobPriority) else self.priority,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy and hasattr(self.retry_policy, "to_dict") else (asdict(self.retry_policy) if self.retry_policy else None),
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        payload = dict(data)
        if "priority" in payload and payload["priority"] is not None:
            payload["priority"] = JobPriority(payload["priority"])
        if "status" in payload and payload["status"] is not None:
            payload["status"] = JobStatus(payload["status"])
        if payload.get("retry_policy") is not None and isinstance(payload["retry_policy"], dict):
            payload["retry_policy"] = RetryPolicy.from_dict(payload["retry_policy"])
        if "args" in payload and payload["args"] is not None:
            payload["args"] = tuple(payload["args"])
        return cls(**payload)
