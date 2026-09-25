"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

import enum
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


class JobPriority(enum.IntEnum):
    """Job execution priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(enum.Enum):
    """Lifecycle status states for a job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    """Configurable exponential backoff retry policy with optional jitter."""

    max_attempts: int = 3
    base_delay: float = 0.05
    backoff_factor: float = 2.0
    jitter: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        """Calculate delay in seconds for the given attempt number (1-based)."""
        delay = self.base_delay * (self.backoff_factor ** max(0, attempt - 1))
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict[str, Any]:
        """Convert RetryPolicy to dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        """Recreate RetryPolicy from dictionary."""
        return cls(
            max_attempts=int(data["max_attempts"]),
            base_delay=float(data.get("base_delay", 0.05)),
            backoff_factor=float(data.get("backoff_factor", 2.0)),
            jitter=bool(data.get("jitter", False)),
        )


@dataclass
class Job:
    """Specification and execution state of a background job."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fn_name: str = ""
    args: tuple[Any, ...] = ()
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
        if not self.job_id:
            self.job_id = str(uuid.uuid4())
        if isinstance(self.args, list):
            self.args = tuple(self.args)
        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        elif isinstance(self.priority, str):
            try:
                self.priority = JobPriority[self.priority.upper()]
            except KeyError:
                self.priority = JobPriority(int(self.priority))
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dictionary representation."""
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if hasattr(self.priority, "value") else int(self.priority),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Recreate Job from dictionary."""
        rp_data = data.get("retry_policy")
        if isinstance(rp_data, RetryPolicy):
            rp = rp_data
        elif isinstance(rp_data, dict):
            rp = RetryPolicy.from_dict(rp_data)
        else:
            rp = None

        raw_priority = data.get("priority", JobPriority.MEDIUM)
        if isinstance(raw_priority, JobPriority):
            priority = raw_priority
        elif isinstance(raw_priority, int):
            priority = JobPriority(raw_priority)
        elif isinstance(raw_priority, str):
            try:
                priority = JobPriority[raw_priority.upper()]
            except KeyError:
                priority = JobPriority(int(raw_priority))
        else:
            priority = JobPriority.MEDIUM

        raw_status = data.get("status", JobStatus.PENDING)
        if isinstance(raw_status, JobStatus):
            status = raw_status
        elif isinstance(raw_status, str):
            status = JobStatus(raw_status)
        else:
            status = JobStatus.PENDING

        return cls(
            job_id=data.get("job_id") or str(uuid.uuid4()),
            fn_name=data.get("fn_name", ""),
            args=tuple(data.get("args", ())),
            kwargs=dict(data.get("kwargs", {})),
            priority=priority,
            status=status,
            retry_policy=rp,
            attempts=int(data.get("attempts", 0)),
            result=data.get("result", None),
            error=data.get("error", None),
            created_at=float(data.get("created_at", time.time())),
            scheduled_at=float(data.get("scheduled_at", 0.0)),
            timeout=float(data["timeout"]) if data.get("timeout") is not None else None,
        )
