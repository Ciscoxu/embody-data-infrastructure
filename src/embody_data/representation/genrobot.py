from __future__ import annotations

import re
from dataclasses import dataclass

from embody_data.representation.stream import SemanticRole, StreamDescriptor


@dataclass(frozen=True, slots=True)
class TopicProfile:
    modality: str
    semantic_role: SemanticRole
    unit: str
    dtype: str
    shape: tuple[int | None, ...]
    encoding: str


_TOPICS: tuple[tuple[re.Pattern[str], TopicProfile], ...] = (
    (
        re.compile(r"^/robot[01]/sensor/camera0/compressed$"),
        TopicProfile("rgb_video", "observation", "not_applicable", "bytes", (None,), "h264"),
    ),
    (
        re.compile(r"^/robot[01]/sensor/camera0/camera_info$"),
        TopicProfile("camera_calibration", "observation", "meter", "float64", (None,), "protobuf"),
    ),
    (
        re.compile(r"^/robot[01]/sensor/imu$"),
        TopicProfile("imu", "observation", "mixed", "float64", (6,), "protobuf"),
    ),
    (
        re.compile(r"^/robot[01]/sensor/magnetic_encoder$"),
        TopicProfile(
            "gripper_opening", "observed_human_motion", "meter", "float64", (1,), "protobuf"
        ),
    ),
    (
        re.compile(r"^/robot[01]/vio/eef_pose$"),
        TopicProfile(
            "pose", "observed_device_pose", "meter+quaternion_xyzw", "float64", (7,), "protobuf"
        ),
    ),
)


def profile_topic(topic: str) -> TopicProfile | None:
    return next((profile for pattern, profile in _TOPICS if pattern.fullmatch(topic)), None)


def stream_id(topic: str) -> str:
    return topic.strip("/").replace("/", "__")


def descriptor_for(topic: str, *, frame_id: str = "unknown") -> StreamDescriptor | None:
    profile = profile_topic(topic)
    if profile is None:
        return None
    coordinate_frame = frame_id or "unknown"
    calibration_id = (
        "unknown"
        if profile.modality in {"rgb_video", "camera_calibration", "imu", "gripper_opening"}
        else "not_applicable"
    )
    return StreamDescriptor(
        stream_id=stream_id(topic),
        modality=profile.modality,
        dtype=profile.dtype,
        shape=profile.shape,
        unit=profile.unit,
        coordinate_frame=coordinate_frame,
        encoding=profile.encoding,
        timestamp_unit="nanosecond",
        clock_domain="device_header_or_mcap_unknown",
        source_fields={"topic": topic},
        collection_mode="human_wearable",
        semantic_role=profile.semantic_role,
        frame_from=coordinate_frame,
        frame_to="unknown",
        transform_direction="unknown",
        calibration_id=calibration_id,
        extensions={
            # Retained for readers of representation v0.1.x. New code should use
            # the typed top-level fields above.
            "collection_mode": "human_wearable",
            "semantic_role": profile.semantic_role,
            "source_embodiment": "Gen DAS dual-hand capture device",
            "target_embodiment": "not_applicable",
        },
    )
