import json
from pathlib import Path

import pytest

from demo.app import DemoStore
from embody_data.errors import EmbodyDataError


def test_demo_registers_folder_bundle_without_copying_raw(tmp_path):
    raw = tmp_path / "bundle"
    raw.mkdir()
    source = raw / "recording.json"
    source.write_text(
        json.dumps(
            {
                "contract_version": "folder_bundle_v1",
                "collection_mode": "human_wearable",
                "semantic_evidence": "Human operated capture device; no robot feedback.",
                "stream_semantics": {
                    "pose": "observed_device_pose",
                    "gripper": "observed_human_motion",
                },
                "stream_semantic_evidence": {
                    "pose": "Pose is measured on the wearable capture device.",
                    "gripper": "Opening is measured from the human-operated gripper.",
                },
                "pose_translation_unit": "meter",
                "gripper_unit": "meter",
                "clock_domains": {"pose": "device_monotonic", "gripper": "device_monotonic"},
                "frames": {"pose": "wearable_base"},
                "video_timestamps_ns": [100, 200],
            }
        ),
        encoding="utf-8",
    )
    (raw / "video.mp4").write_bytes(b"demo-video")
    (raw / "pose.csv").write_text(
        "timestamp_ns,tx,ty,tz,qx,qy,qz,qw\n100,0,0,0,0,0,0,1\n200,0.1,0,0,0,0,0,1\n",
        encoding="utf-8",
    )
    (raw / "gripper.csv").write_text(
        "timestamp_ns,opening\n100,0.02\n200,0.03\n", encoding="utf-8"
    )
    (raw / "calibration.json").write_text(
        json.dumps(
            {
                "K": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "R": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "P": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
                "T_b_c": [0, 0, 0, 0, 0, 0, 1],
                "transform_direction": "camera_to_base",
            }
        ),
        encoding="utf-8",
    )
    store = DemoStore(tmp_path / "workspace")

    record = store.create_recording(
        {
            "source_path": str(raw),
            "input_type": "folder_bundle_v1",
            "collection_mode": "human_wearable",
        }
    )
    run = store.process(record["recording_id"])

    assert run["state"] == "succeeded"
    assert run["manifest"]["collection_mode"] == "human_wearable"
    source_value = json.loads(source.read_text(encoding="utf-8"))
    assert source_value["collection_mode"] == "human_wearable"
    manifest = Path(run["output_path"]) / "metadata" / "processed_manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["source"]["container"]


def test_demo_requires_explicit_valid_collection_mode(tmp_path):
    raw = tmp_path / "fixture.mcap"
    raw.write_bytes(b"not-an-mcap")
    store = DemoStore(tmp_path / "workspace")

    with pytest.raises(EmbodyDataError, match="valid collection mode"):
        store.create_recording(
            {"source_path": str(raw), "input_type": "mcap", "collection_mode": "robot"}
        )


def test_demo_page_exposes_first_batch_workspaces():
    page = Path("demo/platform.html").read_text(encoding="utf-8")

    for label in (
        "Overview",
        "New Ingest",
        "Transfer / Integrity",
        "Recording Detail",
        "Pipeline Run",
        "QC &amp; Artifacts",
    ):
        assert label in page
    assert "Raw immutable" in page
    assert "Demo 不是云上传器" in page
    assert "robot_executed_action" not in page
