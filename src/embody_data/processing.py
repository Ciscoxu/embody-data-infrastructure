from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from embody_data import __version__
from embody_data.calibration import validate_calibrations
from embody_data.decode import AdapterKey, DecodeRequest, dispatch_decode
from embody_data.episode import whole_recording_episode
from embody_data.errors import EmbodyDataError
from embody_data.ingestion import inspect_recording
from embody_data.metadata.source_profiles import resolve_source_profile
from embody_data.qc import build_qc_report
from embody_data.storage.layout import ProcessedRunLayout
from embody_data.sync import synchronize


def process_recording(source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not source.is_file():
        raise EmbodyDataError("raw_not_found", f"Raw MCAP does not exist: {source}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmbodyDataError("output_not_empty", f"Refusing to overwrite: {output_dir}")
    raw_before = _sha256(source)
    layout = ProcessedRunLayout(output_dir)
    for directory in layout.required_directories():
        directory.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {
        "operation": "process_recording",
        "state": "running",
        "started_at": _now(),
        "finished_at": None,
        "source_path": str(source.resolve()),
        "stages": [],
    }
    _write(layout.metadata / "processing_status.json", status)
    try:
        inspect = inspect_recording(source, layout.metadata / "inspect")
        status["stages"].append({"stage": "inspect", "state": "succeeded"})
        profile_decision = inspect.get("profile_decision", {})
        selected_profile = profile_decision.get("selected_profile")
        if profile_decision.get("status") != "confirmed" or not selected_profile:
            raise EmbodyDataError(
                "source_profile_unresolved",
                "A confirmed source profile is required before decoding.",
                {"profile_decision": profile_decision},
            )
        source_profile = resolve_source_profile(str(selected_profile))
        _write(
            layout.metadata / "recording_declaration.json",
            _recording_declaration(source, source_profile, config),
        )
        requested_streams = config.get("streams")
        decoded = dispatch_decode(
            AdapterKey(
                source_profile.container,
                source_profile.encoding,
                source_profile.source_type,
            ),
            DecodeRequest(
                source=source,
                streams_dir=output_dir / "data" / "streams",
                assets_dir=output_dir / "data" / "assets",
                streams=(
                    frozenset(str(value) for value in requested_streams)
                    if isinstance(requested_streams, list)
                    else None
                ),
                start=_optional_int(config.get("start_time_ns")),
                end=_optional_int(config.get("end_time_ns")),
            ),
        )
        status["stages"].append(
            {
                "stage": "decode_normalize",
                "state": "succeeded",
                "failure_count": len(decoded.decode_failures),
            }
        )
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
        episode = whole_recording_episode(source, decoded.timestamps, decoded.descriptors)
        episode_path = output_dir / "data" / "episodes" / f"{episode['episode_id']}.json"
        _write(episode_path, episode)
        status["stages"].append({"stage": "episode", "state": "succeeded"})
        qc = build_qc_report(
            descriptors=decoded.descriptors,
            records=decoded.records,
            sync=sync,
            calibration=calibration,
            decode_failures=decoded.decode_failures,
            video_assets=decoded.video_assets,
        )
        _write(layout.qc / "qc_report.json", qc)
        _write(
            layout.qc / "source_qc.json",
            {"qc_version": qc["qc_version"], "findings": qc["source_findings"]},
        )
        _write(
            layout.qc / "semantic_qc.json",
            {"qc_version": qc["qc_version"], "findings": qc["semantic_findings"]},
        )
        for stream_id, mask in qc["validity_masks"].items():
            _write(layout.qc / "validity_masks" / f"{stream_id}.json", mask)
        status["stages"].append({"stage": "qc", "state": "succeeded", "verdict": qc["verdict"]})
        raw_after = _sha256(source)
        if raw_before != raw_after:
            raise EmbodyDataError("raw_mutated", "Raw input checksum changed during processing.")
        streams = {
            sid: {"path": f"data/streams/{sid}.jsonl", "descriptor": descriptor}
            for sid, descriptor in decoded.descriptors.items()
        }
        processed_topics = {
            descriptor["source_fields"]["topic"] for descriptor in decoded.descriptors.values()
        }
        unprocessed_topics = [
            {
                "topic": topic["topic"],
                "schema_name": topic["schema_name"],
                "message_count": topic["message_count"],
                "reason": "not_in_phase1_mvp_mapping",
            }
            for topic in inspect["topics"]
            if topic["topic"] not in processed_topics
        ]
        manifest = {
            "manifest_version": "0.1.0",
            "representation_version": "0.1.0",
            "source": {
                **source_profile.to_dict(),
                "path": str(source.resolve()),
                "sha256": raw_after,
                "size_bytes": source.stat().st_size,
            },
            "collection_mode": source_profile.collection_mode,
            "trajectory_semantics": source_profile.trajectory_semantics,
            "streams": streams,
            "unprocessed_topics": unprocessed_topics,
            "video_assets": decoded.video_assets,
            "episode_path": episode_path.relative_to(output_dir).as_posix(),
            "calibration_path": "calibration/camera_calibration.json",
            "timestamp_mapping_path": "metadata/timestamp_mapping.json",
            "qc_path": "qc/qc_report.json",
            "inspect_path": "metadata/inspect/topic_summary.json",
            "source_inventory_path": "metadata/inspect/source_inventory.json",
            "profile_decision_path": "metadata/inspect/profile_decision.json",
            "provenance_path": "metadata/provenance.json",
        }
        provenance = {
            "tool": {"name": "embody-data", "version": __version__},
            "processed_at": _now(),
            "config": config,
            "stages": status["stages"],
            "sync_policy": sync.get("policy"),
            "reference_stream": sync.get("reference_stream"),
            "source_timestamp_preserved": True,
            "inspect_duration_ns": inspect["duration_ns"],
            "semantic_assumptions": [
                "Whole recording is one candidate episode.",
                *source_profile.semantic_assumptions,
            ],
        }
        _write(layout.metadata / "provenance.json", provenance)
        _write(layout.metadata / "processed_manifest.json", manifest)
        status["state"] = "succeeded"
        status["finished_at"] = _now()
        _write(layout.metadata / "processing_status.json", status)
        return manifest
    except Exception as exc:
        status["state"] = "failed"
        status["finished_at"] = _now()
        status["error"] = (
            exc.to_dict()
            if isinstance(exc, EmbodyDataError)
            else {"code": "unexpected_error", "message": str(exc)}
        )
        _write(layout.metadata / "processing_status.json", status)
        raise


def process_genrobot_mcap(
    source: Path, output_dir: Path, config: dict[str, Any]
) -> dict[str, Any]:
    """Backward-compatible wrapper for the first registered source adapter."""
    return process_recording(source, output_dir, config)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _recording_declaration(
    source: Path, source_profile: Any, config: dict[str, Any]
) -> dict[str, Any]:
    configured_rights = config.get("rights")
    rights = configured_rights if isinstance(configured_rights, dict) else {}
    return {
        "declaration_version": "0.1.0",
        "source_adapter": "mcap",
        "source_path": str(source.resolve()),
        "collection_mode": source_profile.collection_mode,
        "declared_collection_mode": config.get("declared_collection_mode", "unknown"),
        "semantic_evidence": source_profile.semantic_evidence,
        "trajectory_semantics": source_profile.trajectory_semantics,
        "operator_pseudonym": config.get("operator_pseudonym", "unknown"),
        "device_id": config.get("device_id", "unknown"),
        "rights": {
            key: rights.get(key, "unknown")
            for key in ("consent", "license", "privacy_redaction", "permitted_use")
        },
        "raw_mutation_policy": "read_only",
    }
