from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from embody_data import __version__
from embody_data.errors import EmbodyDataError
from embody_data.purpose.models import PurposeKind, PurposeProfile, PurposeRun
from embody_data.storage.purpose import PurposeRunLayout
from embody_data.storage.reader import ProcessedReader

_IMPLEMENTED = {PurposeKind.ARCHIVAL, PurposeKind.EXPLORATION}
_REJECT_FOR_ALL = {"SOURCE_QC_MISSING"}


def run_purpose(processed_root: Path, output_dir: Path, profile: PurposeProfile) -> PurposeRun:
    """Create a local purpose projection without reading or decoding raw data."""
    if profile.purpose not in _IMPLEMENTED:
        raise EmbodyDataError(
            "purpose_unsupported",
            f"Purpose '{profile.purpose}' is an interface only in Phase 1.",
            {
                "purpose": profile.purpose,
                "implemented": sorted(item.value for item in _IMPLEMENTED),
                "not_implemented": "training, IK, retargeting, and control evaluation",
            },
        )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmbodyDataError("output_not_empty", f"Refusing to overwrite: {output_dir}")

    layout = PurposeRunLayout(output_dir)
    for directory in layout.required_directories():
        directory.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {
        "operation": "run_purpose",
        "state": "running",
        "started_at": _now(),
        "finished_at": None,
        "purpose": profile.purpose,
        "stages": [],
    }
    _write(layout.status, status)
    try:
        reader = ProcessedReader(processed_root)
        manifest_path = processed_root / "metadata" / "processed_manifest.json"
        manifest_sha256 = _sha256(manifest_path)
        source_qc = _read_source_qc(processed_root, reader.manifest)
        normalized_provenance = processed_root / str(
            reader.manifest.get("provenance_path", "metadata/provenance.json")
        )
        artifacts = _build_artifacts(reader, layout, profile, manifest_path)
        validity_masks = _build_validity_masks(reader, layout)
        status["stages"].append(
            {"stage": "derive_local_artifacts", "state": "succeeded", "count": len(artifacts)}
        )
        purpose_qc = _purpose_qc(
            profile=profile,
            source_qc=source_qc,
            provenance_exists=normalized_provenance.is_file(),
            artifact_count=len(artifacts),
        )
        _write(layout.qc, purpose_qc)
        status["stages"].append(
            {"stage": "purpose_qc", "state": "succeeded", "verdict": purpose_qc["verdict"]}
        )
        episode = reader.episode()
        recording_id = str(
            reader.manifest.get("recording_id")
            or Path(str(reader.manifest.get("source", {}).get("path", processed_root.name))).stem
        )
        provenance = {
            "tool": {"name": "embody-data", "version": __version__},
            "created_at": _now(),
            "derivation": "purpose_projection_from_normalized_dataset",
            "raw_decode_performed": False,
            "normalized_data_modified": False,
            "normalized_run": str(processed_root.resolve()),
            "normalized_manifest": str(manifest_path.resolve()),
            "normalized_manifest_sha256": manifest_sha256,
            "normalized_provenance": str(normalized_provenance.resolve()),
            "profile": profile.to_dict(),
        }
        _write(layout.provenance, provenance)
        run = PurposeRun(
            run_id=output_dir.name,
            recording_id=recording_id,
            profile=profile,
            normalized_run=str(processed_root.resolve()),
            normalized_manifest_sha256=manifest_sha256,
            selected_streams=reader.stream_ids(),
            selected_episodes=[str(episode.get("episode_id", "unknown"))],
            artifacts=artifacts,
            validity_masks=validity_masks,
            qc_path=layout.qc.relative_to(output_dir).as_posix(),
            status_path=layout.status.relative_to(output_dir).as_posix(),
            provenance_path=layout.provenance.relative_to(output_dir).as_posix(),
            created_at=_now(),
        )
        _write(layout.manifest, run.to_dict())
        status["state"] = "succeeded"
        status["finished_at"] = _now()
        status["manifest_path"] = layout.manifest.name
        _write(layout.status, status)
        return run
    except Exception as exc:
        status["state"] = "failed"
        status["finished_at"] = _now()
        status["error"] = (
            exc.to_dict()
            if isinstance(exc, EmbodyDataError)
            else {"code": "unexpected_error", "message": str(exc)}
        )
        _write(layout.status, status)
        raise


def _build_artifacts(
    reader: ProcessedReader,
    layout: PurposeRunLayout,
    profile: PurposeProfile,
    manifest_path: Path,
) -> list[dict[str, Any]]:
    if profile.purpose == PurposeKind.ARCHIVAL:
        inventory = {
            "stream_count": len(reader.stream_ids()),
            "file_count": sum(1 for path in reader.root.rglob("*") if path.is_file()),
            "files": [
                {
                    "path": path.relative_to(reader.root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in sorted(path for path in reader.root.rglob("*") if path.is_file())
            ],
            "streams": [
                {
                    "stream_id": stream_id,
                    "path": reader.manifest["streams"][stream_id]["path"],
                    "sha256": _sha256(reader.root / reader.manifest["streams"][stream_id]["path"]),
                }
                for stream_id in reader.stream_ids()
            ],
            "normalized_manifest_sha256": _sha256(manifest_path),
        }
        path = layout.artifacts / "archival_inventory.json"
        _write(path, inventory)
        return [_artifact(path, layout.root, "archival_inventory")]

    stride = max(1, int(profile.options.get("preview_stride", 10)))
    summary: dict[str, Any] = {"streams": {}}
    preview: dict[str, Any] = {"stride": stride, "streams": {}}
    for stream_id in reader.stream_ids():
        rows = list(reader.iter_stream(stream_id))
        timestamps = [int(row["source_timestamp_ns"]) for row in rows]
        descriptor = reader.manifest["streams"][stream_id]["descriptor"]
        summary["streams"][stream_id] = {
            "modality": descriptor["modality"],
            "record_count": len(rows),
            "start_timestamp_ns": min(timestamps) if timestamps else None,
            "end_timestamp_ns": max(timestamps) if timestamps else None,
            "numeric_summary": _numeric_summary(rows),
        }
        preview["streams"][stream_id] = [
            {"source_timestamp_ns": row["source_timestamp_ns"], "data": row.get("data", {})}
            for row in rows[::stride]
        ]
    summary_path = layout.artifacts / "summary_statistics.json"
    preview_path = layout.artifacts / "preview_index.json"
    _write(summary_path, summary)
    _write(preview_path, preview)
    return [
        _artifact(summary_path, layout.root, "summary_statistics"),
        _artifact(preview_path, layout.root, "preview_index"),
    ]


def _numeric_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    values: dict[str, list[float]] = {}
    for row in rows:
        for key, value in _flatten_numeric(row.get("data", {})):
            if math.isfinite(value):
                values.setdefault(key, []).append(value)
    return {
        key: {
            "count": len(items),
            "min": min(items),
            "max": max(items),
            "mean": sum(items) / len(items),
        }
        for key, items in sorted(values.items())
        if items
    }


def _flatten_numeric(value: Any, prefix: str = "") -> Iterable[tuple[str, float]]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield prefix or "value", float(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_numeric(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            yield from _flatten_numeric(child, child_prefix)


def _purpose_qc(
    *,
    profile: PurposeProfile,
    source_qc: dict[str, Any],
    provenance_exists: bool,
    artifact_count: int,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for finding in source_qc.get("findings", []):
        severity = str(finding.get("severity", "warn"))
        reason_code = str(finding.get("reason_code", "UNKNOWN_SOURCE_FINDING"))
        disposition = "allowed"
        purpose_severity = "pass"
        if reason_code in _REJECT_FOR_ALL:
            disposition = "rejected"
            purpose_severity = "fail"
        elif profile.purpose == PurposeKind.EXPLORATION and severity in {"warn", "fail"}:
            disposition = "degraded"
            purpose_severity = "warn"
        decisions.append(
            {
                "source_severity": severity,
                "reason_code": reason_code,
                "disposition": disposition,
                "purpose_severity": purpose_severity,
                "source_finding": finding,
            }
        )
    local_findings: list[dict[str, Any]] = []
    if not provenance_exists:
        local_findings.append({"severity": "fail", "reason_code": "NORMALIZED_PROVENANCE_MISSING"})
    if artifact_count == 0:
        local_findings.append({"severity": "fail", "reason_code": "PURPOSE_ARTIFACT_MISSING"})
    levels = [item["purpose_severity"] for item in decisions] + [
        item["severity"] for item in local_findings
    ]
    return {
        "purpose_qc_version": "0.1.0",
        "profile": profile.to_dict(),
        "verdict": _max_severity(levels),
        "source_qc_verdict": source_qc.get("verdict", "unknown"),
        "source_findings_preserved": True,
        "decisions": decisions,
        "findings": local_findings,
    }


def _build_validity_masks(
    reader: ProcessedReader, layout: PurposeRunLayout
) -> list[dict[str, Any]]:
    value = {
        "mask_version": "0.1.0",
        "meaning": "stream_selected_for_purpose",
        "streams": {stream_id: True for stream_id in reader.stream_ids()},
    }
    path = layout.validity_masks / "selected_streams.json"
    _write(path, value)
    return [_artifact(path, layout.root, "selected_streams_validity")]


def _max_severity(levels: list[str]) -> str:
    order = {"pass": 0, "warn": 1, "fail": 2}
    return max(levels, key=lambda level: order.get(level, 2), default="pass")


def _read_source_qc(processed_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = processed_root / str(manifest.get("qc_path", "qc/qc_report.json"))
    if not path.is_file():
        return {
            "verdict": "unknown",
            "findings": [{"severity": "fail", "reason_code": "SOURCE_QC_MISSING"}],
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"verdict": "unknown", "findings": []}


def _artifact(path: Path, root: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


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
