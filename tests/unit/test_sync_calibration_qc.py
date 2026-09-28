from embody_data.calibration import validate_calibrations
from embody_data.qc import build_qc_report, build_validity_masks
from embody_data.sync import synchronize


def test_timestamp_mapping_preserves_source_and_reports_errors():
    result = synchronize(
        {"camera": [0, 10, 20], "imu": [1, 11, 100]}, reference_stream="camera", max_delta_ns=5
    )
    assert result["streams"]["imu"]["mapping"][0]["source_timestamp_ns"] == 1
    assert result["streams"]["imu"]["coverage"] == 2 / 3
    assert result["streams"]["imu"]["error_ns"]["max"] == 80


def test_calibration_and_qc_reason_codes():
    calibration = validate_calibrations(
        [
            {
                "data": {
                    "calibration_id": "bad",
                    "K": [1.0],
                    "R": [1.0] * 9,
                    "P": [1.0] * 12,
                    "T_b_c": [0.0] * 7,
                    "transform_direction": "unknown",
                }
            }
        ]
    )
    reasons = {finding["reason_code"] for finding in calibration["findings"]}
    assert "CALIBRATION_ARRAY_LENGTH" in reasons
    assert "CALIBRATION_QUATERNION_NORM" in reasons

    report = build_qc_report(
        descriptors={},
        records={},
        sync={"streams": {}},
        calibration={"findings": []},
        decode_failures=[],
        video_assets=[],
    )
    assert report["verdict"] == "fail"
    assert "REQUIRED_MODALITY_MISSING" in {item["reason_code"] for item in report["findings"]}
    assert report["findings"] == report["semantic_findings"] + report["source_findings"]


def test_timestamp_gap_is_attributed_to_its_own_stream():
    report = build_qc_report(
        descriptors={},
        records={},
        sync={
            "streams": {
                "steady": {
                    "non_monotonic": 0,
                    "duplicates": 0,
                    "coverage": 1.0,
                    "gap_ns": {"median": 10, "max": 10},
                    "mapping": [],
                },
                "gapped": {
                    "non_monotonic": 0,
                    "duplicates": 0,
                    "coverage": 1.0,
                    "gap_ns": {"median": 10, "max": 1_000_000_001},
                    "mapping": [],
                },
            }
        },
        calibration={"findings": []},
        decode_failures=[],
        video_assets=[],
    )
    gaps = [item for item in report["source_findings"] if item["reason_code"] == "TIMESTAMP_GAP"]
    assert gaps == [
        {
            "severity": "warn",
            "reason_code": "TIMESTAMP_GAP",
            "stream_id": "gapped",
            "median_gap_ns": 10,
            "max_gap_ns": 1_000_000_001,
        }
    ]


def test_validity_mask_preserves_sync_and_source_invalid_reasons():
    masks = build_validity_masks(
        records={
            "pose": [
                {"source_timestamp_ns": 0, "data": {"valid": True}},
                {"source_timestamp_ns": 10, "data": {"valid": False}},
            ]
        },
        sync={
            "streams": {
                "pose": {
                    "mapping": [
                        {"source_timestamp_ns": 0, "valid": True},
                        {"source_timestamp_ns": 10, "valid": False},
                    ]
                }
            }
        },
    )
    samples = masks["pose"]["samples"]
    assert samples[0]["valid"] is True
    assert samples[1]["valid"] is False
    assert samples[1]["reason_codes"] == (
        "SYNC_DELTA_EXCEEDED",
        "SOURCE_MARKED_INVALID",
    )
