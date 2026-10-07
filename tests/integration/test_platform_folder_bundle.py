import json

from embody_data.platform import PlatformService
from embody_data.storage import ProcessedReader


def test_folder_bundle_runs_through_platform_service(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "recording.json").write_text(
        json.dumps(
            {
                "contract_version": "folder_bundle_v1",
                "collection_mode": "human_wearable",
                "semantic_evidence": "Operator wore the capture device; no robot feedback exists.",
                "pose_translation_unit": "meter",
                "gripper_unit": "meter",
                "clock_domains": {"pose": "device_monotonic", "gripper": "device_monotonic"},
                "frames": {"pose": "wearable_base"},
                "video_timestamps_ns": [100, 200],
                "stream_semantics": {
                    "pose": "observed_device_pose",
                    "gripper": "observed_human_motion",
                },
                "stream_semantic_evidence": {
                    "pose": "Pose is measured from the human-operated capture device.",
                    "gripper": "Encoder is attached to the human-operated gripper.",
                },
            }
        ),
        encoding="utf-8",
    )
    (raw / "video.mp4").write_bytes(b"demo-not-a-real-video")
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
    service = PlatformService(tmp_path / "platform")
    project = service.create_project("demo", project_id="project-demo")
    recording = service.register_recording(
        project["project_id"], raw, adapter_name="folder_bundle_v1", recording_id="recording-demo"
    )
    run = service.run(recording["recording_id"], run_id="run-demo")

    assert run["state"] == "succeeded"
    reader = ProcessedReader(
        tmp_path
        / "platform/projects/project-demo/recordings/recording-demo/runs/run-demo"
    )
    assert reader.stream_ids() == ["gripper", "pose"]
    pose = next(reader.iter_stream("pose"))
    assert pose["semantic_role"] == "observed_device_pose"
    assert pose["collection_mode"] == "human_wearable"
    qc = json.loads(
        (
            tmp_path
            / "platform"
            / "projects"
            / "project-demo"
            / "recordings"
            / "recording-demo"
            / "runs"
            / "run-demo"
            / "qc"
            / "qc_report.json"
        ).read_text(encoding="utf-8")
    )
    assert qc["verdict"] in {"pass", "warn"}
    assert all(
        finding["reason_code"] != "BILATERAL_STREAM_COVERAGE"
        for finding in qc["findings"]
    )
    status = json.loads(
        (
            tmp_path
            / "platform"
            / "projects"
            / "project-demo"
            / "recordings"
            / "recording-demo"
            / "runs"
            / "run-demo"
            / "metadata"
            / "processing_status.json"
        ).read_text(encoding="utf-8")
    )
    episode_stage = next(item for item in status["stages"] if item["stage"] == "episode")
    assert episode_stage["boundary_strategy"] == "whole_recording"
    declaration = json.loads(
        (
            tmp_path
            / "platform"
            / "projects"
            / "project-demo"
            / "recordings"
            / "recording-demo"
            / "runs"
            / "run-demo"
            / "metadata"
            / "recording_declaration.json"
        ).read_text(encoding="utf-8")
    )
    assert declaration["collection_mode"] == "human_wearable"
    assert declaration["trajectory_semantics"]["pose"] == "observed_device_pose"
    assert declaration["rights"]["consent"] == "unknown"
    assert (raw / "pose.csv").read_text(encoding="utf-8").startswith("timestamp_ns")
