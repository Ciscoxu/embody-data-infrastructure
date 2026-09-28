from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class OperationStatus:
    operation: str
    state: RunState
    started_at: str
    finished_at: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def started(cls, operation: str) -> OperationStatus:
        return cls(operation=operation, state=RunState.RUNNING, started_at=utc_now())

    def finish(self, *, succeeded: bool) -> None:
        self.state = RunState.SUCCEEDED if succeeded else RunState.FAILED
        self.finished_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
