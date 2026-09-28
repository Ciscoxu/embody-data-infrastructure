from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TextIO

from embody_data.decode.base import AdapterKey, DecodeRequest, register_adapter
from embody_data.decode.mcap import header_fields, iter_decoded
from embody_data.metadata.source_profiles import GENROBOT_REALOMIN
from embody_data.representation.genrobot import descriptor_for, profile_topic, stream_id
from embody_data.representation.stream import NormalizedRecord


@dataclass(slots=True)
class DecodeResult:
    descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)
    timestamps: dict[str, list[int]] = field(default_factory=dict)
    records: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calibration_messages: list[dict[str, Any]] = field(default_factory=list)
    decode_failures: list[dict[str, Any]] = field(default_factory=list)
    video_assets: list[dict[str, Any]] = field(default_factory=list)


def decode_recording(
    path: Path,
    streams_dir: Path,
    assets_dir: Path,
    *,
    streams: set[str] | frozenset[str] | None = None,
    start: int | None = None,
    end: int | None = None,
) -> DecodeResult:
    """Decode selected streams and the half-open MCAP log-time range ``[start, end)``."""
    streams_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    result = DecodeResult()
    with ExitStack() as stack:
        handles: dict[str, TextIO] = {}
        video_handles: dict[str, Any] = {}
        video_offsets: dict[str, int] = {}
        video_metadata: dict[str, dict[str, Any]] = {}
        topics = _selected_topics(streams)
        for message in iter_decoded(
            path, topics=topics, start_time_ns=start, end_time_ns=end
        ):
            profile = profile_topic(message.topic)
            if profile is None:
                continue
            sid = stream_id(message.topic)
            header_ns, sequence, frame_id = header_fields(message.decoded)
            source_ns = header_ns if header_ns is not None else message.publish_time_ns
            timestamp_kind = "protobuf_header" if header_ns is not None else "mcap_publish"
            try:
                payload, extensions = _normalize_payload(message.topic, message.decoded)
            except (AttributeError, TypeError, ValueError) as exc:
                result.decode_failures.append(
                    {"topic": message.topic, "log_time_ns": message.log_time_ns, "reason": str(exc)}
                )
                continue
            if profile.modality == "rgb_video":
                binary = payload.pop("compressed_bytes")
                asset = assets_dir / f"{sid}.h264"
                if sid not in video_handles:
                    video_handles[sid] = stack.enter_context(asset.open("wb"))
                    video_offsets[sid] = 0
                    video_metadata[sid] = {
                        "stream_id": sid,
                        "path": asset.name,
                        "encoding": "h264",
                        "frame_count": 0,
                    }
                    result.video_assets.append(video_metadata[sid])
                offset = video_offsets[sid]
                video_handles[sid].write(binary)
                video_offsets[sid] += len(binary)
                payload.update(asset=asset.name, byte_offset=offset, byte_length=len(binary))
                video_metadata[sid]["frame_count"] += 1
            record = NormalizedRecord(
                stream_id=sid,
                topic=message.topic,
                source_path=str(path.resolve()),
                source_timestamp_ns=source_ns,
                source_timestamp_kind=timestamp_kind,
                clock_domain="protobuf_header_unknown" if header_ns is not None else "mcap_publish",
                log_time_ns=message.log_time_ns,
                publish_time_ns=message.publish_time_ns,
                header_timestamp_ns=header_ns,
                sequence_id=sequence,
                frame_id=frame_id,
                data=payload,
                extensions=extensions,
            )
            if sid not in handles:
                handles[sid] = stack.enter_context(
                    (streams_dir / f"{sid}.jsonl").open("w", encoding="utf-8")
                )
                descriptor = descriptor_for(message.topic, frame_id=frame_id)
                if descriptor:
                    result.descriptors[sid] = asdict(descriptor)
                result.timestamps[sid] = []
                result.records[sid] = []
            row = asdict(record)
            handles[sid].write(json.dumps(row, sort_keys=True) + "\n")
            result.timestamps[sid].append(source_ns)
            if profile.modality in {"pose", "gripper_opening", "camera_calibration"}:
                result.records[sid].append(row)
            if profile.modality == "camera_calibration":
                result.calibration_messages.append(row)
    for asset_record in result.video_assets:
        asset_record["decode_validation"] = _validate_h264(assets_dir / asset_record["path"])
    return result


def _selected_topics(streams: set[str] | frozenset[str] | None) -> set[str] | None:
    if streams is None:
        return None
    return {value if value.startswith("/") else f"/{value.replace('__', '/')}" for value in streams}


class GenRobotMcapAdapter:
    key = AdapterKey("mcap", "protobuf", GENROBOT_REALOMIN.source_type)
    name = "genrobot_realomin_mcap"
    version = "0.1.0"

    def decode(self, request: DecodeRequest) -> DecodeResult:
        return decode_recording(
            request.source,
            request.streams_dir,
            request.assets_dir,
            streams=request.streams,
            start=request.start,
            end=request.end,
        )


GENROBOT_MCAP_ADAPTER = GenRobotMcapAdapter()
register_adapter(GENROBOT_MCAP_ADAPTER)


def _normalize_payload(topic: str, message: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = profile_topic(topic)
    if profile is None:
        raise ValueError(f"unsupported topic: {topic}")
    raw = _message_dict(message)
    descriptor = getattr(message, "DESCRIPTOR", None)
    source = raw if getattr(descriptor, "full_name", "") == "google.protobuf.Struct" else message
    payload: dict[str, Any]
    if profile.modality == "rgb_video":
        value = _get(source, "data")
        if isinstance(value, str):
            value = value.encode()
        if not isinstance(value, bytes):
            raise TypeError("compressed image data is not bytes")
        payload = {"compressed_bytes": value, "format": str(_get(source, "format", default="h264"))}
    elif profile.modality == "imu":
        payload = {
            "angular_velocity": _vector(source, "angular_velocity"),
            "angular_velocity_unit": "radian_per_second",
            "linear_acceleration": _vector(source, "linear_acceleration"),
            "linear_acceleration_unit": "g_force",
        }
    elif profile.modality == "gripper_opening":
        payload = {"opening": float(_get(source, "value")), "unit": "meter"}
    elif profile.modality == "pose":
        payload = {
            "translation": _vector(source, "pose.position"),
            "translation_unit": "meter",
            "quaternion_xyzw": _quaternion(source, "pose.orientation"),
            "source_frame": str(_get(source, "frame_id", default="unknown") or "unknown"),
            "target_frame": "unknown",
            "transform_direction": "unknown",
            "calibration_id": "not_applicable",
            "valid": bool(_get(source, "pose_valid", default=True)),
        }
    else:
        transform = [float(value) for value in _list(source, "T_b_c")]
        payload = {
            "width": int(_get(source, "width", default=0)),
            "height": int(_get(source, "height", default=0)),
            "distortion_model": str(
                _get(source, "distortion_model", default="unknown") or "unknown"
            ),
            "D": [float(value) for value in _list(source, "D")],
            "K": [float(value) for value in _list(source, "K")],
            "R": [float(value) for value in _list(source, "R")],
            "P": [float(value) for value in _list(source, "P")],
            "T_b_c": transform,
            "translation_unit": "meter",
            "source_frame": str(_get(source, "frame_id", default="unknown") or "unknown"),
            "target_frame": "base_frame_unknown",
            "transform_direction": "camera_to_base" if transform else "unknown",
        }
        payload["calibration_id"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]
    return payload, {"vendor_message": raw}


def _message_dict(message: Any) -> dict[str, Any]:
    try:
        from google.protobuf.json_format import MessageToDict  # type: ignore[import-untyped]

        value = MessageToDict(message, preserving_proto_field_name=True)
        return value if isinstance(value, dict) else {"value": value}
    except (ImportError, TypeError):
        return {"type": type(message).__name__}


def _get(value: Any, path: str, *, default: Any = None) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            current = getattr(current, part, default)
        if current is default:
            break
    return current


def _list(value: Any, path: str) -> list[Any]:
    result = _get(value, path, default=[])
    return list(result) if result is not None else []


def _vector(value: Any, path: str) -> list[float]:
    return [float(_get(value, f"{path}.{axis}", default=0.0)) for axis in ("x", "y", "z")]


def _quaternion(value: Any, path: str) -> list[float]:
    return [float(_get(value, f"{path}.{axis}", default=0.0)) for axis in ("x", "y", "z", "w")]


def _validate_h264(path: Path, *, frame_limit: int = 3) -> dict[str, Any]:
    try:
        import av
    except ImportError:
        return {"state": "unavailable", "reason": "video_extra_not_installed"}
    try:
        decoded = 0
        width = None
        height = None
        with av.open(str(path), format="h264") as container:
            for frame in container.decode(video=0):
                decoded += 1
                width, height = frame.width, frame.height
                if decoded >= frame_limit:
                    break
        return {"state": "succeeded", "decoded_frames": decoded, "width": width, "height": height}
    except Exception as exc:
        return {"state": "failed", "reason": type(exc).__name__}
