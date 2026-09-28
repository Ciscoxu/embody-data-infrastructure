# General Internal Representation

The Phase 1 representation is a minimal, evolvable adapter boundary—not an
industry or customer schema.

Every stream must carry: `stream_id`, `modality`, timestamps, data or references,
dtype, shape, unit, coordinate frame, encoding, validity/confidence, source-field
mapping, extensions, `collection_mode`, `semantic_role`, and
`representation_version`.

Unknown facts are explicit (`unknown` or `not_applicable`). Normalization must not
silently discard source fields; preserve them in extensions when no common field
exists.

Every recording declares `human_wearable`, `teleop_device_only`, or
`teleop_robot`. Every action-like stream declares whether it is observed human
motion, observed device pose, teleop command, robot measured state, robot
commanded/executed action, derived action, retargeted action, or unknown.
Topic names and vendor field names are not semantic evidence by themselves.
Derived and retargeted streams retain their source fields, algorithm/config
version, target embodiment, and validity.
