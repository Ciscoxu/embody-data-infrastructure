from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PlatformRunState = Literal["pending", "running", "succeeded", "failed"]


@dataclass(slots=True)
class ProjectRecord:
    project_id: str
    name: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecordingRecord:
    recording_id: str
    project_id: str
    source_adapter: str
    source_path: str
    collection_mode: str
    semantic_evidence: str
    registered_at: str
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    project_id: str
    recording_id: str
    state: PlatformRunState
    output_path: str
    created_at: str
    finished_at: str | None = None
    error: dict[str, Any] | None = None
    manifest_path: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
