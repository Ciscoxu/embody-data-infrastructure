from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures.genrobot_fixture import write_genrobot_fixture  # noqa: E402


def write_folder_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "recording.json").write_text(
        json.dumps(
            {
                "contract_version": "folder_bundle_v1",
                "collection_mode": "human_wearable",
                "semantic_evidence": "Human-operated device; no robot feedback is present.",
                "stream_semantics": {
                    "pose": "observed_device_pose",
                    "gripper": "observed_human_motion",
                },
                "stream_semantic_evidence": {
                    "pose": "Pose is measured on the wearable capture device.",
                    "gripper": "Opening is measured from the human-operated gripper.",
                },
                "clock_domains": {
                    "pose": "device_monotonic",
                    "gripper": "device_monotonic",
                },
                "frames": {"pose": "wearable_base", "gripper": "not_applicable"},
                "frame_from": {"pose": "wearable_base"},
                "frame_to": {"pose": "device_eef"},
                "transform_direction": {"pose": "device_eef_to_wearable_base"},
                "pose_translation_unit": "meter",
                "gripper_unit": "meter",
                "calibration_id": "demo-calibration-v1",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "pose.csv").write_text(
        "timestamp_ns,tx,ty,tz,qx,qy,qz,qw\n"
        "1000000000,0,0,0,0,0,0,1\n"
        "1033000000,0.1,0,0,0,0,0,1\n",
        encoding="utf-8",
    )
    (root / "gripper.csv").write_text(
        "timestamp_ns,opening\n1000000000,0.02\n1033000000,0.03\n",
        encoding="utf-8",
    )
    (root / "calibration.json").write_text(
        json.dumps(
            {
                "K": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "R": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "P": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
                "T_b_c": [0, 0, 0, 0, 0, 0, 1],
                "source_frame": "camera",
                "target_frame": "wearable_base",
                "transform_direction": "camera_to_base",
                "calibration_id": "demo-calibration-v1",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate tiny MCAP and folder-bundle samples.")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path(".local/demo-sample/fixture.mcap"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mcap = write_genrobot_fixture(args.output)
    folder = write_folder_bundle(args.output.parent / "folder_bundle_v1")
    print(f"MCAP: {mcap.resolve()}")
    print(f"folder_bundle_v1: {folder.resolve()}")


if __name__ == "__main__":
    main()
