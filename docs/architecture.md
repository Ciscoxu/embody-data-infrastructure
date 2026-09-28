# Architecture

Phase 1 is a replaceable staged pipeline for human-collected MEgo/wearable and
teleoperation data. Source-specific decoders produce a general internal
representation; downstream stages must not import vendor types.

| Module | Owns | Does not own |
|---|---|---|
| `ingestion` | content-based inspector registry, discovery, inventory, checksums | full payload decoding |
| `decode` | source/schema deserialization | synchronization policy |
| `representation` | common stream contracts | stable release schema |
| `sync` | reference timeline and alignment | coordinate transforms |
| `calibration` | frame graph and transforms | timestamp repair |
| `episode` | segmentation and derived data | raw mutation |
| `qc` | findings, masks, verdict policy | silent data deletion |
| `metadata` | collection mode, manifests, rights, provenance | semantic guessing or binary payload layout |
| `storage` | local layout and I/O interfaces | cloud-provider coupling |

The first supported source should be a small human-collected MCAP sample, added
as a decoder plugin plus reproducible synthetic fixtures. Collection mode and
action-like signal semantics are resolved outside vendor parsing. Phase 2 cloud
storage, Phase 3 schema registry, and Phase 4 distribution remain outside the
current package boundary.

Only the MCAP/embedded-Protobuf GenRobot path is currently registered, but the
orchestrator is format-neutral. Inspection adapters match source content, source
profiles own container/encoding and semantic contracts, and decoder adapters are
selected by `(container, encoding, source_profile)`. Supporting another format
adds registrations at those boundaries rather than branches in `processing.py`.

Within Phase 1, the local pipeline is split into four layers: source discovery
and classification, source adaptation and decode, a vendor-neutral semantic
processing core, and purpose-specific local outputs. These layers are separate
from the Phase 1–4 product roadmap. See `local_pipeline_four_layers.md` for the
contracts and implementation status.
