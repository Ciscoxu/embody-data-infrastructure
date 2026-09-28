from __future__ import annotations

from pathlib import Path
from typing import Any

from google.protobuf.struct_pb2 import Struct
from mcap_protobuf.writer import Writer


def write_genrobot_fixture(
    path: Path, *, bad_quaternion: bool = False, bad_gripper: bool = False
) -> Path:
    base = 1_700_000_000_000_000_000
    messages: dict[str, dict[str, Any]] = {
        "/robot0/sensor/camera0/compressed": {"data": "fixture-h264", "format": "h264"},
        "/robot0/sensor/camera0/camera_info": {
            "frame_id": "camera0_optical",
            "width": 640,
            "height": 480,
            "distortion_model": "plumb_bob",
            "D": [0.0, 0.0, 0.0, 0.0, 0.0],
            "K": [500.0, 0.0, 320.0, 0.0, 500.0, 240.0, 0.0, 0.0, 1.0],
            "R": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "P": [500.0, 0.0, 320.0, 0.0, 0.0, 500.0, 240.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            "T_b_c": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0],
        },
        "/robot0/sensor/imu": {
            "frame_id": "imu0",
            "angular_velocity": {"x": 0.1, "y": 0.2, "z": 0.3},
            "linear_acceleration": {"x": 0.0, "y": 0.0, "z": 1.0},
        },
        "/robot0/sensor/magnetic_encoder": {"value": "invalid" if bad_gripper else 0.05},
        "/robot0/vio/eef_pose": {
            "frame_id": "vio_world",
            "pose": {
                "position": {"x": 0.1, "y": 0.2, "z": 0.3},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 2.0 if bad_quaternion else 1.0},
            },
            "pose_valid": True,
        },
    }
    with Writer(str(path)) as writer:
        for index in range(3):
            timestamp = base + index * 33_000_000
            for topic, fields in messages.items():
                message = Struct()
                message.update(fields)
                writer.write_message(topic, message, log_time=timestamp, publish_time=timestamp)
    return path
