# Processing QC Rules

QC findings use stable rule IDs and contain severity, reason, affected range, and
repairability. Episode verdicts are `pass`, `warning`, `repairable`, or `reject`.

The MVP rule families are ingestion/decode, timestamp/sync, camera, pose, and
human-collection semantic consistency. Critical streams also expose timestep or
frame validity masks. Reports record the rule/config version and remain beside
processed data.

Semantic QC rejects unsupported promotions such as human/device pose labeled as
robot executed action, or retargeted action without a target embodiment and
derivation record. Governance QC reports missing consent, license,
privacy/redaction, or permitted-use metadata as explicit unknown/warning states;
it never invents those values.
