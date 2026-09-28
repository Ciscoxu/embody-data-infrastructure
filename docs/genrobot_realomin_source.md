# GenRobot RealOmin MCAP source profile

- Source type: `genrobot_realomin_mcap`
- Container: `mcap`
- Encoding: `protobuf`
- Dataset: `genrobot2025/10Kh-RealOmin-OpenData`
- License: CC BY-SA 4.0
- Access: gated; accepting terms and Hugging Face authentication are required
- Collection mode: `human_wearable`
- Evidence: human-operated Gen DAS dual-hand/gripper capture device; no robot
  execution feedback is established by this profile

This is the only currently registered full processing path, not a hard-coded
pipeline contract. The MCAP inspector identifies the container by content, and
the confirmed profile supplies the adapter key and semantic contract to the
generic processing orchestrator.

## Topic semantics

- `/robot*/sensor/camera0/compressed`: H.264 sensor observation
- `/robot*/sensor/camera0/camera_info`: camera calibration observation
- `/robot*/sensor/imu`: angular velocity in rad/s and linear acceleration kept
  as g-force per vendor documentation
- `/robot*/sensor/magnetic_encoder`: observed gripper opening, meter, expected
  range 0–0.103 m
- `/robot*/vio/eef_pose`: `observed_device_pose`, translation in meters and
  quaternion XYZW

`robot0`/`robot1` are device-side names and are not robot-action evidence.
Vendor H5 `action == eef_pos` is a copy and would be `derived_action`; the MVP
does not emit it. Unknown pose direction/frame information remains unknown.
Camera `T_b_c` is accepted only when present and is recorded as camera-to-base;
missing extrinsics are never replaced with identity.

## Failure and output contract

Acquisition refuses unknown sizes, selections over five files, and selections
over the byte limit. It never downloads a repository snapshot. Gate/auth errors
write `blocked_auth` to `acquisition_status.json`. Processing refuses a nonempty
output directory, checks that the raw SHA-256 is unchanged, and writes stage
status even when a stage fails.

The MVP physical format is inspectable JSON/JSONL with compressed H.264 assets.
It is a Phase 1 internal representation, not a stable release schema.

## First real validation

Revision `fcbc0d38550e134f273426aa7c9cc2b491270bc4` was validated with
`Clutter Tidy-Up [Stage2]/00001/01708.mcap`. The recording contains bilateral
camera0, IMU, magnetic encoder, EEF pose, `RobotInfo`, and `SystemInfo` topics.
It does not contain camera calibration, so QC correctly reports
`REQUIRED_MODALITY_MISSING`; no identity extrinsic is invented. `RobotInfo` and
`SystemInfo` remain listed as unprocessed MVP topics and do not promote the
recording to `teleop_robot` without execution semantics evidence.
