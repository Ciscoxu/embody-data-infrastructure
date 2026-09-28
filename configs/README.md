# Configuration

Configuration is separated by pipeline stage. JSON and TOML are supported by the
base loader; YAML is supported when the optional `yaml` dependency is installed.
Never store secrets here. Commit small reproducible MVP configs only.

Configuration axes remain separate: `sources/` owns container/profile and
collection evidence, `processing/` owns synchronization/calibration/episode
policy, and `purposes/` owns local downstream acceptance and artifacts. A source
profile must never imply robot-action semantics or a downstream purpose.
