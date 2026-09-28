from __future__ import annotations

import math
from typing import Any


def validate_calibrations(messages: list[dict[str, Any]]) -> dict[str, Any]:
    calibrations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for message in messages:
        data = message["data"]
        calibration_id = data["calibration_id"]
        checks = {"K": 9, "R": 9, "P": 12, "T_b_c": 7}
        for field, length in checks.items():
            values = data[field]
            if len(values) != length:
                findings.append(
                    _finding("fail", "CALIBRATION_ARRAY_LENGTH", calibration_id, field, len(values))
                )
            elif not all(math.isfinite(value) for value in values):
                findings.append(
                    _finding("fail", "CALIBRATION_NONFINITE", calibration_id, field, len(values))
                )
        transform = data["T_b_c"]
        if len(transform) == 7:
            norm = math.sqrt(sum(value * value for value in transform[3:]))
            if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
                findings.append(
                    {
                        "severity": "fail",
                        "reason_code": "CALIBRATION_QUATERNION_NORM",
                        "calibration_id": calibration_id,
                        "value": norm,
                    }
                )
        if data["transform_direction"] == "unknown":
            findings.append(
                {
                    "severity": "warn",
                    "reason_code": "CALIBRATION_DIRECTION_UNKNOWN",
                    "calibration_id": calibration_id,
                }
            )
        calibrations.append(data)
    return {"calibrations": calibrations, "findings": findings}


def _finding(
    severity: str, reason: str, calibration_id: str, field: str, actual: int
) -> dict[str, Any]:
    return {
        "severity": severity,
        "reason_code": reason,
        "calibration_id": calibration_id,
        "field": field,
        "actual_length": actual,
    }
