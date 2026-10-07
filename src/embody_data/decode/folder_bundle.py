from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from embody_data.decode.base import AdapterKey, DecodeRequest, register_adapter
from embody_data.decode.genrobot import DecodeResult
from embody_data.errors import EmbodyDataError
from embody_data.representation.stream import NormalizedRecord, StreamDescriptor

FOLDER_BUNDLE_KEY = AdapterKey("folder_bundle", "csv_json", "folder_bundle_v1")
SEMANTIC_ROLES = {
    "observation", "observed_human_motion", "observed_device_pose", "teleop_command",
    "robot_measured_state", "robot_commanded_action", "robot_executed_action",
    "derived_action", "retargeted_action", "unknown",
}


def decode_folder_bundle(request: DecodeRequest) -> DecodeResult:
    root = request.source
    if not root.is_dir():
        raise EmbodyDataError("bundle_not_directory", "folder_bundle_v1 input must be a directory.")
    manifest_path = root / "recording.json"
    if not manifest_path.is_file():
        raise EmbodyDataError(
            "bundle_manifest_missing", "folder_bundle_v1 requires recording.json."
        )
    manifest = _load_json(manifest_path)
    if manifest.get("contract_version") != "folder_bundle_v1":
        raise EmbodyDataError(
            "bundle_contract_unsupported",
            "recording.json must declare contract_version=folder_bundle_v1.",
            {"contract_version": manifest.get("contract_version")},
        )
    mode = manifest.get("collection_mode")
    if mode not in {"human_wearable", "teleop_device_only", "teleop_robot"}:
        raise EmbodyDataError(
            "collection_mode_invalid",
            "recording.json must declare a supported collection_mode.",
            {"collection_mode": mode},
        )
    if not str(manifest.get("semantic_evidence", "")).strip():
        raise EmbodyDataError(
            "semantic_evidence_missing",
            "recording.json must explain the evidence for collection_mode.",
        )
    if mode == "teleop_robot":
        raise EmbodyDataError(
            "teleop_robot_evidence_missing",
            "folder_bundle_v1 cannot verify synchronized robot feedback in this demo.",
            {"required": ["teleop_command", "robot_measured_state_or_executed_action"]},
        )

    request.streams_dir.mkdir(parents=True, exist_ok=True)
    request.assets_dir.mkdir(parents=True, exist_ok=True)
    result = DecodeResult()
    specs = {
        "imu": ("imu.csv", "imu", _imu_data),
        "pose": (
            "pose.csv",
            "pose",
            _pose_data,
        ),
        "gripper": (
            "gripper.csv",
            "gripper_opening",
            _gripper_data,
        ),
    }
    requested = set(request.streams) if request.streams else None
    for stream_id, (filename, modality, parser) in specs.items():
        if requested is not None and stream_id not in requested:
            continue
        path = root / filename
        if not path.is_file():
            continue
        role = str(manifest.get("stream_semantics", {}).get(stream_id, ""))
        role_evidence = str(manifest.get("stream_semantic_evidence", {}).get(stream_id, ""))
        if role not in SEMANTIC_ROLES or not role_evidence.strip():
            raise EmbodyDataError(
                "stream_semantics_invalid",
                "Each present CSV stream requires a valid semantic role and evidence.",
                {"stream_id": stream_id, "semantic_role": role},
            )
        _validate_role(mode, stream_id, role, manifest)
        descriptor = StreamDescriptor(
            stream_id=stream_id,
            modality=modality,
            dtype="float64",
            shape=(None,),
            unit=_unit(modality),
            coordinate_frame=str(manifest.get("frames", {}).get(stream_id, "unknown")),
            encoding="csv",
            timestamp_unit="nanosecond",
            clock_domain=str(manifest.get("clock_domains", {}).get(stream_id, "unknown")),
            source_fields={"path": filename, "timestamp": "timestamp_ns"},
            collection_mode=mode,
            semantic_role=role,  # type: ignore[arg-type]
            frame_from=str(manifest.get("frame_from", {}).get(stream_id, "unknown")),
            frame_to=str(manifest.get("frame_to", {}).get(stream_id, "unknown")),
            transform_direction=str(
                manifest.get("transform_direction", {}).get(stream_id, "unknown")
            ),
            calibration_id=str(manifest.get("calibration_id", "unknown")),
            extensions={"folder_bundle_version": "1", "semantic_evidence": role_evidence},
        )
        result.descriptors[stream_id] = asdict(descriptor)
        result.timestamps[stream_id] = []
        result.records[stream_id] = []
        output = request.streams_dir / f"{stream_id}.jsonl"
        with path.open(encoding="utf-8-sig", newline="") as source, output.open(
            "w", encoding="utf-8"
        ) as target:
            for index, row in enumerate(csv.DictReader(source)):
                try:
                    timestamp = int(row["timestamp_ns"])
                    if request.start is not None and timestamp < request.start:
                        continue
                    if request.end is not None and timestamp >= request.end:
                        continue
                    data = parser(row, manifest)
                    record = NormalizedRecord(
                        stream_id=stream_id,
                        topic=filename,
                        source_path=str(path.resolve()),
                        source_timestamp_ns=timestamp,
                        source_timestamp_kind="csv_timestamp_ns",
                        clock_domain=descriptor.clock_domain,
                        log_time_ns=timestamp,
                        publish_time_ns=timestamp,
                        header_timestamp_ns=None,
                        sequence_id=index,
                        frame_id=descriptor.coordinate_frame,
                        data=data,
                        extensions={"source_row": row},
                        collection_mode=mode,
                        semantic_role=descriptor.semantic_role,
                        coordinate_frame=descriptor.coordinate_frame,
                        transform_direction=descriptor.transform_direction,
                        calibration_id=descriptor.calibration_id,
                    )
                    value = asdict(record)
                    target.write(json.dumps(value, sort_keys=True) + "\n")
                    result.timestamps[stream_id].append(timestamp)
                    result.records[stream_id].append(value)
                except (KeyError, TypeError, ValueError) as exc:
                    result.decode_failures.append(
                        {"path": filename, "row": index + 2, "reason": str(exc)}
                    )

    video = root / "video.mp4"
    if video.is_file() and (requested is None or "video" in requested):
        descriptor = StreamDescriptor(
            stream_id="video",
            modality="rgb_video",
            dtype="uint8",
            shape=(None, None, 3),
            unit="not_applicable",
            coordinate_frame=str(manifest.get("frames", {}).get("video", "unknown")),
            encoding="mp4",
            timestamp_unit="nanosecond",
            clock_domain=str(manifest.get("clock_domains", {}).get("video", "unknown")),
            source_fields={"path": "video.mp4"},
            collection_mode=mode,
            semantic_role="observation",
            calibration_id=str(manifest.get("calibration_id", "unknown")),
        )
        result.descriptors["video"] = asdict(descriptor)
        timestamps = [int(value) for value in manifest.get("video_timestamps_ns", [])]
        result.timestamps["video"] = timestamps
        result.records["video"] = []
        result.video_assets.append(
            {
                "stream_id": "video",
                "path": str(video.resolve()),
                "encoding": "mp4",
                "frame_count": len(timestamps),
                "sha256": _sha256(video),
                "decode_validation": {
                    "state": "unavailable",
                    "reason": "external_asset_not_decoded",
                },
            }
        )

    calibration_path = root / "calibration.json"
    if calibration_path.is_file():
        calibration = _load_json(calibration_path)
        calibration.setdefault("K", [])
        calibration.setdefault("R", [])
        calibration.setdefault("P", [])
        calibration.setdefault("T_b_c", [])
        calibration.setdefault("transform_direction", "unknown")
        calibration.setdefault("calibration_id", _sha256(calibration_path)[:16])
        result.calibration_messages.append({"data": calibration})
        result.descriptors["calibration"] = asdict(
            StreamDescriptor(
                stream_id="calibration",
                modality="camera_calibration",
                dtype="object",
                shape=(),
                unit="not_applicable",
                coordinate_frame=str(calibration.get("source_frame", "unknown")),
                encoding="json",
                timestamp_unit="not_applicable",
                clock_domain="not_applicable",
                source_fields={"path": "calibration.json"},
                collection_mode=mode,
                semantic_role="observation",
                calibration_id=str(calibration["calibration_id"]),
            )
        )
    return result


class FolderBundleAdapter:
    key = FOLDER_BUNDLE_KEY
    name = "folder_bundle_v1"
    version = "0.1.0"

    def decode(self, request: DecodeRequest) -> DecodeResult:
        return decode_folder_bundle(request)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmbodyDataError(
            "bundle_json_invalid", f"Unable to read {path.name}.", {"reason": str(exc)}
        ) from exc
    if not isinstance(value, dict):
        raise EmbodyDataError("bundle_json_invalid", f"{path.name} must contain an object.")
    return value


def _number(row: dict[str, str], *names: str) -> float:
    for name in names:
        if name in row and row[name] != "":
            return float(row[name])
    raise KeyError("/".join(names))


def _imu_data(row: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "linear_acceleration": [_number(row, "ax"), _number(row, "ay"), _number(row, "az")],
        "linear_acceleration_unit": str(manifest.get("imu_acceleration_unit", "unknown")),
        "angular_velocity": [_number(row, "gx"), _number(row, "gy"), _number(row, "gz")],
        "angular_velocity_unit": str(manifest.get("imu_angular_velocity_unit", "unknown")),
    }


def _pose_data(row: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "translation": [_number(row, "tx", "x"), _number(row, "ty", "y"), _number(row, "tz", "z")],
        "translation_unit": str(manifest.get("pose_translation_unit", "unknown")),
        "quaternion_xyzw": [
            _number(row, "qx"),
            _number(row, "qy"),
            _number(row, "qz"),
            _number(row, "qw"),
        ],
    }


def _gripper_data(row: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "opening": _number(row, "opening", "value"),
        "unit": str(manifest.get("gripper_unit", "unknown")),
    }


def _unit(modality: str) -> str:
    return {"imu": "mixed", "pose": "mixed", "gripper_opening": "unknown"}[modality]


def _validate_role(mode: str, stream_id: str, role: str, manifest: dict[str, Any]) -> None:
    robot_roles = {"robot_measured_state", "robot_commanded_action", "robot_executed_action"}
    if mode == "human_wearable" and (role == "teleop_command" or role in robot_roles):
        raise EmbodyDataError(
            "semantic_role_incompatible",
            "human_wearable streams cannot claim teleop or robot execution semantics.",
            {"stream_id": stream_id, "semantic_role": role, "collection_mode": mode},
        )
    if mode == "teleop_device_only" and role in robot_roles:
        raise EmbodyDataError(
            "semantic_role_incompatible",
            "teleop_device_only has no verified robot state or execution feedback.",
            {"stream_id": stream_id, "semantic_role": role, "collection_mode": mode},
        )
    if role in {"derived_action", "retargeted_action"}:
        provenance = manifest.get("derivation_provenance", {}).get(stream_id)
        if not isinstance(provenance, dict) or not provenance.get("transformation"):
            raise EmbodyDataError(
                "derivation_provenance_missing",
                "Derived and retargeted actions require transformation provenance.",
                {"stream_id": stream_id, "semantic_role": role},
            )
    if role == "retargeted_action" and not manifest.get("target_embodiment"):
        raise EmbodyDataError(
            "target_embodiment_missing",
            "retargeted_action requires a target embodiment.",
            {"stream_id": stream_id},
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


FOLDER_BUNDLE_ADAPTER = FolderBundleAdapter()
register_adapter(FOLDER_BUNDLE_ADAPTER)
