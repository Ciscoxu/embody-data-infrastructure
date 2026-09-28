from __future__ import annotations

import math
from typing import Any

from embody_data.qc.masks import build_validity_masks


def build_source_qc_facts(
    *,
    sync: dict[str, Any],
    decode_failures: list[dict[str, Any]],
    video_assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return transport/time facts without applying a downstream purpose policy."""
    findings: list[dict[str, Any]] = []
    for stream_id, details in sync.get("streams", {}).items():
        if details["non_monotonic"]:
            findings.append(_finding("fail", "TIMESTAMP_NON_MONOTONIC", stream_id=stream_id))
        if details["duplicates"]:
            findings.append(
                _finding(
                    "warn",
                    "TIMESTAMP_DUPLICATE",
                    stream_id=stream_id,
                    count=details["duplicates"],
                )
            )
        if details["coverage"] < 0.9:
            findings.append(
                _finding(
                    "warn",
                    "SYNC_LOW_COVERAGE",
                    stream_id=stream_id,
                    coverage=details["coverage"],
                )
            )
        gap = details.get("gap_ns", {})
        median_gap = gap.get("median")
        max_gap = gap.get("max")
        if median_gap and max_gap and max_gap > max(5 * median_gap, 1_000_000_000):
            findings.append(
                _finding(
                    "warn",
                    "TIMESTAMP_GAP",
                    stream_id=stream_id,
                    median_gap_ns=median_gap,
                    max_gap_ns=max_gap,
                )
            )
    for failure in decode_failures:
        findings.append(_finding("fail", "DECODE_FAILURE", **failure))
    if not video_assets:
        findings.append(_finding("fail", "VIDEO_STREAM_MISSING"))
    else:
        for asset in video_assets:
            if asset["frame_count"] <= 0:
                findings.append(_finding("fail", "VIDEO_EMPTY", stream_id=asset["stream_id"]))
            validation = asset.get("decode_validation", {})
            if validation.get("state") == "succeeded" and validation.get("decoded_frames", 0) <= 0:
                findings.append(
                    _finding("fail", "VIDEO_DECODE_ZERO_FRAMES", stream_id=asset["stream_id"])
                )
            elif validation.get("state") != "succeeded":
                findings.append(
                    _finding(
                        "warn",
                        "VIDEO_DECODE_UNVERIFIED",
                        stream_id=asset["stream_id"],
                        validation=validation,
                    )
                )
    return findings


def build_semantic_qc_facts(
    *,
    descriptors: dict[str, dict[str, Any]],
    records: dict[str, list[dict[str, Any]]],
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return representation/calibration facts without changing source semantics."""
    findings: list[dict[str, Any]] = list(calibration["findings"])
    modalities = {value["modality"] for value in descriptors.values()}
    for modality in ("rgb_video", "camera_calibration", "imu", "gripper_opening", "pose"):
        if modality not in modalities:
            findings.append(_finding("fail", "REQUIRED_MODALITY_MISSING", modality=modality))
    hands = {"robot0" if "robot0" in sid else "robot1" for sid in descriptors}
    if hands != {"robot0", "robot1"}:
        findings.append(_finding("warn", "BILATERAL_STREAM_COVERAGE", observed=sorted(hands)))
    for stream_id, rows in records.items():
        modality = descriptors[stream_id]["modality"]
        if modality == "pose":
            for index, row in enumerate(rows):
                quaternion = row["data"]["quaternion_xyzw"]
                norm = math.sqrt(sum(value * value for value in quaternion))
                if not math.isclose(norm, 1.0, rel_tol=1e-2, abs_tol=1e-2):
                    findings.append(
                        _finding(
                            "fail",
                            "POSE_QUATERNION_NORM",
                            stream_id=stream_id,
                            index=index,
                            value=norm,
                        )
                    )
        elif modality == "gripper_opening":
            for index, row in enumerate(rows):
                value = row["data"]["opening"]
                if not 0.0 <= value <= 0.103:
                    findings.append(
                        _finding(
                            "fail",
                            "GRIPPER_RANGE",
                            stream_id=stream_id,
                            index=index,
                            value=value,
                        )
                    )
    for descriptor in descriptors.values():
        if descriptor["coordinate_frame"] == "unknown":
            findings.append(
                _finding(
                    "warn",
                    "METADATA_UNKNOWN",
                    field="coordinate_frame",
                    stream_id=descriptor["stream_id"],
                )
            )
    return findings


def build_qc_report(
    *,
    descriptors: dict[str, dict[str, Any]],
    records: dict[str, list[dict[str, Any]]],
    sync: dict[str, Any],
    calibration: dict[str, Any],
    decode_failures: list[dict[str, Any]],
    video_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the legacy aggregate report plus independently consumable facts."""
    semantic_findings = build_semantic_qc_facts(
        descriptors=descriptors,
        records=records,
        calibration=calibration,
    )
    source_findings = build_source_qc_facts(
        sync=sync,
        decode_failures=decode_failures,
        video_assets=video_assets,
    )
    findings = semantic_findings + source_findings
    severity = {"pass": 0, "warn": 1, "fail": 2}
    verdict = max(
        (finding["severity"] for finding in findings),
        key=lambda item: severity[str(item)],
        default="pass",
    )
    return {
        "qc_version": "0.2.0",
        "verdict": verdict,
        "summary": {
            level: sum(item["severity"] == level for item in findings) for level in severity
        },
        "findings": findings,
        "source_findings": source_findings,
        "semantic_findings": semantic_findings,
        "validity_masks": build_validity_masks(records=records, sync=sync),
    }


def _finding(severity: str, reason_code: str, **details: Any) -> dict[str, Any]:
    return {"severity": severity, "reason_code": reason_code, **details}
