# Human-Collected Embodied Data Infrastructure Agent Guide

## Project focus

Build the processing foundation for embodied data collected by people through
MEgo-style wearable/egocentric devices or teleoperation systems. Work on
**Phase 0 and the Phase 1 MVP** in `EXECUTION_PLAN.md`.

The current source is human activity, not autonomous robot rollout data. Keep
the collection mode and semantic origin of every trajectory explicit. Do not
add cloud orchestration, model training, customer delivery, or a stable
industry-wide schema unless the user explicitly changes phase or scope.

## Collection modes

Every recording must declare one collection mode:

- `human_wearable`: human motion captured by an ego/wearable device. Pose and
  gripper signals describe the person or capture device, not a robot command.
- `teleop_device_only`: teleoperator intent/device signals without verified
  robot execution feedback.
- `teleop_robot`: operator command plus synchronized robot state/feedback.

Never infer `teleop_robot` from filenames, topic names, or an `action` field.
If evidence is incomplete, preserve the source field and use the less assertive
semantic classification.

## Non-negotiable data rules

- Treat raw inputs as immutable source-of-truth data.
- Write every generated artifact to a separate output directory.
- Preserve source timestamps, clock domains, and reference-timeline mappings.
- Every spatial field must declare units, coordinate frames, transform
  direction, and calibration identity, or explicitly use `unknown` /
  `not_applicable`.
- Distinguish observed human/device trajectory, teleoperation command, robot
  measured state, robot executed action, and derived/retargeted action.
- Never label a human or wearable trajectory as robot action without a
  documented retargeting/control transformation and target embodiment.
- A copied or shifted pose sequence is `derived_action`, not verified
  `commanded_action` or `executed_action`.
- Emit structured status, errors, QC results, and provenance; logs alone are
  not an output contract.
- Keep source-specific fields in extension metadata instead of silently
  dropping them during normalization.
- Record consent, license, privacy/redaction status, operator pseudonym, and
  permitted-use metadata when available. Unknown values stay unknown.

## Architecture boundaries

- Python uses a `src/` layout under the `embody_data` package.
- Keep source/transport parsing such as MCAP and Protobuf in `decode/`;
  downstream modules depend on `representation/`.
- Keep collection-profile mapping and semantic classification explicit; do not
  bury them in vendor decoder logic.
- Keep temporal alignment in `sync/` and spatial transforms in `calibration/`.
- Keep episode derivation in `episode/`, validation policy in `qc/`, and output
  manifests in `metadata/`.
- `storage/` in Phase 1 only defines local paths and interfaces. Do not import a
  cloud SDK into processing code.
- Prefer small typed models and pure functions. Avoid a single pipeline module
  that owns every stage.

## Current MVP source contract

Prioritize one small MCAP sample from a human wearable or teleoperation capture
system. Start with 2-5 recordings and these modalities when present:

- egocentric/fisheye RGB video
- IMU
- observed EEF/device pose
- gripper opening or magnetic encoder
- camera calibration

Treat tactile, stereo depth, point cloud, robot feedback, and retargeting as
extensions unless the selected sample requires them. Unit tests must continue
to use small synthetic fixtures; do not commit large or gated source data.

## Development workflow

1. Read the relevant Phase 1 subsection and source profile before editing.
2. Identify collection mode, input, output, assumptions, action semantics, and
   failure behavior.
3. Add or update unit tests; add an integration test for cross-module behavior.
4. Run `python -m pytest` and `python -m ruff check .` when available.
5. Inspect structured artifacts, not only process exit codes.
6. Report changed files, phase/subphase, metadata/config changes, verification,
   known limits, and the next compatible interface.

## Completion standard

A task is complete only when it has an implementation, structured outputs or
status, a reproducible test/sample, documented semantic assumptions, and known
limitations. Never overwrite raw fixtures or existing processed runs. Never
claim policy-ready robot action output unless its semantics and derivation have
been validated.
