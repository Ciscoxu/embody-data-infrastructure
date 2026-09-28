---
name: phase1-implementation
description: Implements scoped Phase 1 processing for human-collected embodied data from MEgo-style wearable/ego devices or teleoperation systems. Use when adding or changing MCAP inspect, decode, representation, synchronization, calibration, episode, QC, processed-output, or reader capabilities in this repository; do not use for model training or generic robotics code.
---

# Human-Collected Phase 1 Implementation

## Classify the source before implementation

Read the matching Phase 1 subsection in `EXECUTION_PLAN.md` and the nearest
`AGENTS.md`. Classify every source as one of:

- `human_wearable`
- `teleop_device_only`
- `teleop_robot`

Record the evidence for that classification. Topic names such as `robot0`, an
HDF5 dataset named `action`, or a vendor converter are not sufficient proof of
robot command or execution semantics.

For each time-varying control-like field, classify it as:

- `observed_human_motion`
- `observed_device_pose`
- `teleop_command`
- `robot_measured_state`
- `robot_commanded_action`
- `robot_executed_action`
- `derived_action`
- `retargeted_action`
- `unknown`

## Workflow

1. Identify the stage input, output, configuration, provenance, failure model,
   collection mode, and action semantics.
2. Implement the smallest vertical slice without later-phase infrastructure.
3. Preserve raw timestamps, clock domains, sequence IDs, source fields, units,
   frames, calibration identity, and collection-device identity.
4. Keep vendor/MCAP/Protobuf parsing behind decoder interfaces.
5. Preserve human/device trajectories as observations unless a documented
   transformation creates a separately named derived or retargeted action.
6. Emit machine-readable status, errors, QC details, and semantic provenance.
7. Add unit coverage and an integration or fixture-based verification.
8. Run the checks declared in `pyproject.toml` and inspect output artifacts.

## Current MVP profile

Prefer a small human-collected MCAP sample with RGB, IMU, observed EEF/device
pose, gripper opening, and camera calibration. Support selective topic and time
range reads. Treat tactile, stereo depth, point cloud, retargeting, and robot
feedback as optional extensions.

The MVP may register only one concrete format/profile path, but orchestration
must resolve inspectors, profiles, and decoders through their registries. Keep
container, encoding, collection mode, and trajectory semantics in the selected
source contract rather than hard-coding them in CLI or processing entry points.

Do not commit large or gated recordings. Create synthetic fixtures that model
normal data, a missing topic, timestamp gaps, clock reset, decode failure, and
tracking loss.

## Stage boundaries

- Source/schema dispatch belongs in `decode/`.
- Normalized stream and source-semantic labels belong in `representation/`.
- Time mapping and error metrics belong in `sync/`.
- Frame graphs and transforms belong in `calibration/`.
- Trimming, segmentation, and derived trajectories belong in `episode/`.
- Rules, findings, verdicts, and validity masks belong in `qc/`.
- Collection mode, manifests, rights metadata, and field descriptions belong
  in `metadata/`.
- Local layout and I/O interfaces belong in `storage/`.

## Completion report

Report the Phase/subphase, collection mode, changed files, inputs/outputs,
action/trajectory semantics, new config or metadata, verification results,
known limits, and the next compatible interface.
