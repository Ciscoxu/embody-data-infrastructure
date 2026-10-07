from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from embody_data.calibration import validate_calibrations
from embody_data.decode import DecodeRequest, dispatch_decode
from embody_data.decode.folder_bundle import FOLDER_BUNDLE_KEY
from embody_data.errors import EmbodyDataError
from embody_data.qc import build_qc_report
from embody_data.storage.layout import ProcessedRunLayout
from embody_data.sync import synchronize


def process_folder_bundle(source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not source.is_dir():
        raise EmbodyDataError("raw_not_found", f"Raw bundle does not exist: {source}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmbodyDataError("output_not_empty", f"Refusing to overwrite: {output_dir}")
    layout = ProcessedRunLayout(output_dir)
    for directory in layout.required_directories():
        directory.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {
        "operation": "process_folder_bundle",
        "state": "running",
        "started_at": _now(),
        "finished_at": None,
        "source_path": str(source.resolve()),
        "stages": [],
    }
    _write(layout.metadata / "processing_status.json", status)
    try:
        inventory_before = _inventory(source)
        inspect_dir = layout.metadata / "inspect"
        _write(
            inspect_dir / "raw_manifest.json",
            {
                "manifest_version": "0.1.0",
                "source_path": str(source.resolve()),
                "files": inventory_before,
            },
        )
        _write(
            inspect_dir / "source_inventory.json",
            {
                "container": "folder_bundle",
                "encoding": "csv_json",
                "files": inventory_before,
            },
        )
        _write(
            inspect_dir / "profile_decision.json",
            {
                "status": "confirmed",
                "selected_profile": "folder_bundle_v1",
                "evidence": [{"source": "recording_contract", "confidence": "high"}],
            },
        )
        _write(inspect_dir / "ingestion_status.json", {"state": "succeeded"})
        status["stages"].append({"stage": "inspect", "state": "succeeded"})
        decoded = dispatch_decode(
            FOLDER_BUNDLE_KEY,
            DecodeRequest(
                source=source,
                streams_dir=output_dir / "data" / "streams",
                assets_dir=output_dir / "data" / "assets",
                streams=(
                    frozenset(config["streams"])
                    if isinstance(config.get("streams"), list)
                    else None
                ),
                start=_optional_int(config.get("start_time_ns")),
                end=_optional_int(config.get("end_time_ns")),
            ),
        )
        status["stages"].append({"stage": "decode_normalize", "state": "succeeded"})
        sync = synchronize(
            decoded.timestamps,
            reference_stream=config.get("reference_stream"),
            max_delta_ns=int(config.get("max_sync_delta_ns", 50_000_000)),
        )
        _write(layout.metadata / "timestamp_mapping.json", sync)
        status["stages"].append({"stage": "synchronize", "state": "succeeded"})
        calibration = validate_calibrations(decoded.calibration_messages)
        _write(output_dir / "calibration" / "camera_calibration.json", calibration)
        status["stages"].append({"stage": "calibration", "state": "succeeded"})
        metadata = json.loads((source / "recording.json").read_text(encoding="utf-8"))
        _write(
            layout.metadata / "recording_declaration.json",
            _recording_declaration(source, metadata, config),
        )
        required_modalities = metadata.get("required_modalities")
        if not isinstance(required_modalities, list):
            required_modalities = sorted(
                {descriptor["modality"] for descriptor in decoded.descriptors.values()}
            )
        all_times = [item for values in decoded.timestamps.values() for item in values]
        episode = {
            "episode_id": "recording-folder-bundle",
            "source_recording": str(source.resolve()),
            "collection_mode": next(
                (value["collection_mode"] for value in decoded.descriptors.values()), "unknown"
            ),
            "start_timestamp_ns": min(all_times) if all_times else None,
            "end_timestamp_ns": max(all_times) if all_times else None,
            "boundary_strategy": "whole_recording",
            "execution_success": "unknown",
        }
        episode_path = output_dir / "data" / "episodes" / "recording-folder-bundle.json"
        _write(episode_path, episode)
        status["stages"].append(
            {
                "stage": "episode",
                "state": "succeeded",
                "episode_id": episode["episode_id"],
                "boundary_strategy": episode["boundary_strategy"],
            }
        )
        qc = build_qc_report(
            descriptors=decoded.descriptors,
            records=decoded.records,
            sync=sync,
            calibration=calibration,
            decode_failures=decoded.decode_failures,
            video_assets=decoded.video_assets,
            required_modalities=tuple(str(value) for value in required_modalities),
            require_bilateral=bool(metadata.get("require_bilateral", False)),
            gripper_range=_gripper_range(metadata),
            require_video="rgb_video" in required_modalities,
        )
        _write(layout.qc / "qc_report.json", qc)
        for stream_id, mask in qc["validity_masks"].items():
            _write(layout.qc / "validity_masks" / f"{stream_id}.json", mask)
        manifest = {
            "manifest_version": "0.1.0",
            "representation_version": "0.1.0",
            "source": {
                "container": "folder_bundle",
                "encoding": "csv_json",
                "path": str(source.resolve()),
            },
            "collection_mode": metadata["collection_mode"],
            "semantic_evidence": metadata["semantic_evidence"],
            "trajectory_semantics": metadata.get("stream_semantics", {}),
            "streams": {
                sid: {"path": f"data/streams/{sid}.jsonl", "descriptor": descriptor}
                for sid, descriptor in decoded.descriptors.items()
                if sid not in {"video", "calibration"}
            },
            "video_assets": decoded.video_assets,
            "episode_path": episode_path.relative_to(output_dir).as_posix(),
            "calibration_path": "calibration/camera_calibration.json",
            "timestamp_mapping_path": "metadata/timestamp_mapping.json",
            "qc_path": "qc/qc_report.json",
            "provenance_path": "metadata/provenance.json",
        }
        _write(
            layout.metadata / "provenance.json",
            {
                "processed_at": _now(),
                "adapter": {"name": "folder_bundle_v1", "version": "0.1.0"},
                "config": config,
                "source_timestamp_preserved": True,
                "raw_mutation_policy": "read_only",
                "semantic_assumptions": ["Whole recording is one candidate episode."],
            },
        )
        _write(layout.metadata / "processed_manifest.json", manifest)
        if inventory_before != _inventory(source):
            raise EmbodyDataError(
                "raw_mutated", "Raw bundle checksums changed during processing."
            )
        status["stages"].append({"stage": "qc", "state": "succeeded", "verdict": qc["verdict"]})
        status["state"] = "succeeded"
        status["finished_at"] = _now()
        _write(layout.metadata / "processing_status.json", status)
        return manifest
    except Exception as exc:
        status["state"] = "failed"
        status["finished_at"] = _now()
        status["error"] = exc.to_dict() if isinstance(exc, EmbodyDataError) else {
            "code": "unexpected_error", "message": str(exc)
        }
        _write(layout.metadata / "processing_status.json", status)
        raise


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _recording_declaration(
    source: Path, metadata: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    configured_rights = config.get("rights")
    source_rights = metadata.get("rights")
    rights = configured_rights if isinstance(configured_rights, dict) else source_rights
    if not isinstance(rights, dict):
        rights = {}
    return {
        "declaration_version": "0.1.0",
        "source_adapter": "folder_bundle_v1",
        "source_path": str(source.resolve()),
        "collection_mode": metadata["collection_mode"],
        "declared_collection_mode": config.get("declared_collection_mode", "unknown"),
        "semantic_evidence": metadata["semantic_evidence"],
        "trajectory_semantics": metadata.get("stream_semantics", {}),
        "operator_pseudonym": config.get(
            "operator_pseudonym", metadata.get("operator_pseudonym", "unknown")
        ),
        "device_id": config.get("device_id", metadata.get("device_id", "unknown")),
        "rights": {
            key: rights.get(key, "unknown")
            for key in ("consent", "license", "privacy_redaction", "permitted_use")
        },
        "raw_mutation_policy": "read_only",
    }


def _gripper_range(metadata: dict[str, Any]) -> tuple[float, float] | None:
    value = metadata.get("gripper_valid_range")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return (float(value[0]), float(value[1]))


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "read_status": "readable",
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
