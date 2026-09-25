"""Data models, enums, retry policies, and serialization for taskflow."""

import enum
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


class JobPriority(enum.IntEnum):
    """Job priority levels. Higher numbers represent higher priority."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(str, enum.Enum):
    """Job lifecycle statuses."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    """Configures retry behavior for failed jobs."""
    max_attempts: int = 3
    base_delay: float = 0.05
    backoff_factor: float = 2.0
    jitter: bool = False

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        """Calculates backoff delay for the given attempt index (1-based)."""
        exp = attempt - 1 if attempt >= 1 else 0
        delay = self.base_delay * (self.backoff_factor ** exp)
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict:
        """Serialize RetryPolicy to dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryPolicy":
        """Reconstruct RetryPolicy from dictionary."""
        return cls(
            max_attempts=int(data.get("max_attempts", 3)),
            base_delay=float(data.get("base_delay", 0.05)),
            backoff_factor=float(data.get("backoff_factor", 2.0)),
            jitter=bool(data.get("jitter", False)),
        )


@dataclass
class Job:
    """Represents a scheduled or executed unit of work."""
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

    def __post_init__(self):
        if not self.job_id:
            self.job_id = str(uuid.uuid4())
        if not isinstance(self.args, tuple):
            self.args = tuple(self.args) if self.args is not None else ()
        if self.kwargs is None:
            self.kwargs = {}
        elif not isinstance(self.kwargs, dict):
            self.kwargs = dict(self.kwargs)
        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)
        if isinstance(self.retry_policy, dict):
            self.retry_policy = RetryPolicy.from_dict(self.retry_policy)

    def to_dict(self) -> dict:
        """Returns JSON-serializable dictionary representation."""
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if hasattr(self.priority, "value") else int(self.priority),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy is not None else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """Recreates Job from a dictionary."""
        d = dict(data)
        rp_data = d.get("retry_policy")
        retry_policy = None
        if rp_data is not None:
            if isinstance(rp_data, RetryPolicy):
                retry_policy = rp_data
            elif isinstance(rp_data, dict):
                retry_policy = RetryPolicy.from_dict(rp_data)

        priority_val = d.get("priority", JobPriority.MEDIUM)
        if isinstance(priority_val, JobPriority):
            priority = priority_val
        elif isinstance(priority_val, int):
            priority = JobPriority(priority_val)
        elif isinstance(priority_val, str) and hasattr(JobPriority, priority_val):
            priority = JobPriority[priority_val]
        else:
            priority = JobPriority(int(priority_val))

        status_val = d.get("status", JobStatus.PENDING)
        if isinstance(status_val, JobStatus):
            status = status_val
        elif isinstance(status_val, str):
            try:
                status = JobStatus(status_val)
            except ValueError:
                status = JobStatus[status_val.upper()]
        else:
            status = JobStatus(status_val)

        return cls(
            job_id=d.get("job_id") or str(uuid.uuid4()),
            fn_name=d.get("fn_name", ""),
            args=tuple(d.get("args", ())),
            kwargs=dict(d.get("kwargs", {})),
            priority=priority,
            status=status,
            retry_policy=retry_policy,
            attempts=int(d.get("attempts", 0)),
            result=d.get("result", None),
            error=d.get("error", None),
            created_at=float(d.get("created_at", time.time())),
            scheduled_at=float(d.get("scheduled_at", 0.0)),
            timeout=float(d["timeout"]) if d.get("timeout") is not None else None,
        )
