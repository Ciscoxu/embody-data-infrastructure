from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CollectionMode = Literal["human_wearable", "teleop_device_only", "teleop_robot"]
DecisionConfidence = Literal["low", "medium", "high"]
ProfileDecisionStatus = Literal["confirmed", "ambiguous", "unknown"]


@dataclass(frozen=True, slots=True)
class FileRecord:
    relative_path: str
    size_bytes: int
    sha256: str | None
    read_status: str
    error: str | None = None


@dataclass(slots=True)
class RawManifest:
    manifest_version: str
    source_id: str
    recording_id: str
    session_id: str | None
    source_path: str
    files: list[FileRecord]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClassificationEvidence:
    source: str
    detail: str
    confidence: DecisionConfidence


@dataclass(frozen=True, slots=True)
class CollectionModeDecision:
    mode: CollectionMode
    confidence: DecisionConfidence
    evidence: tuple[ClassificationEvidence, ...]


@dataclass(frozen=True, slots=True)
class ProfileCandidate:
    profile: str
    confidence: DecisionConfidence
    evidence: tuple[ClassificationEvidence, ...]


@dataclass(frozen=True, slots=True)
class ProfileDecision:
    status: ProfileDecisionStatus
    selected_profile: str | None
    candidates: tuple[ProfileCandidate, ...]
    evidence: tuple[ClassificationEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceStreamInventory:
    stream_id: str
    schema_name: str
    schema_encoding: str
    message_encoding: str
    message_count: int
    first_log_time_ns: int | None
    last_log_time_ns: int | None


@dataclass(frozen=True, slots=True)
class ClockEvidence:
    clock_domain: str
    timestamp_kind: str
    source: str


@dataclass(frozen=True, slots=True)
class RightsMetadata:
    consent: str = "unknown"
    license: str = "unknown"
    privacy_redaction: str = "unknown"
    operator_pseudonym: str = "unknown"
    permitted_use: str = "unknown"


@dataclass(frozen=True, slots=True)
class SourceInventory:
    inventory_version: str
    source_object_identity: str
    source_path: str
    files: tuple[FileRecord, ...]
    container: str
    schemas: tuple[str, ...]
    streams: tuple[SourceStreamInventory, ...]
    timestamp_candidates: tuple[str, ...]
    clock_evidence: tuple[ClockEvidence, ...]
    calibration_candidates: tuple[str, ...]
    frame_candidates: tuple[str, ...]
    profile_decision: ProfileDecision
    collection_mode: CollectionModeDecision | None
    rights: RightsMetadata

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
