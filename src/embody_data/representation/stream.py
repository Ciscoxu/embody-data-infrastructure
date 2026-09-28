from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CollectionMode = Literal["human_wearable", "teleop_device_only", "teleop_robot", "unknown"]
SemanticRole = Literal[
    "observation",
    "observed_human_motion",
    "observed_device_pose",
    "teleop_command",
    "robot_measured_state",
    "robot_commanded_action",
    "robot_executed_action",
    "derived_action",
    "retargeted_action",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class StreamDescriptor:
    stream_id: str
    modality: str
    dtype: str
    shape: tuple[int | None, ...]
    unit: str
    coordinate_frame: str
    encoding: str
    timestamp_unit: str
    clock_domain: str
    source_fields: dict[str, str]
    collection_mode: CollectionMode = "unknown"
    semantic_role: SemanticRole = "unknown"
    frame_from: str = "unknown"
    frame_to: str = "unknown"
    transform_direction: str = "unknown"
    calibration_id: str = "unknown"
    representation_version: str = "0.1.0"
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    stream_id: str
    topic: str
    source_path: str
    source_timestamp_ns: int
    source_timestamp_kind: str
    clock_domain: str
    log_time_ns: int
    publish_time_ns: int
    header_timestamp_ns: int | None
    sequence_id: int | str | None
    frame_id: str
    data: dict[str, Any]
    extensions: dict[str, Any] = field(default_factory=dict)
    collection_mode: CollectionMode = "unknown"
    semantic_role: SemanticRole = "unknown"
    coordinate_frame: str = "unknown"
    transform_direction: str = "unknown"
    calibration_id: str = "unknown"
    valid: bool | None = None
    confidence: float | None = None
