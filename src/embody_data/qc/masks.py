from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ValiditySample:
    source_timestamp_ns: int | None
    valid: bool
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StreamValidityMask:
    stream_id: str
    mask_version: str
    samples: tuple[ValiditySample, ...]


def build_validity_masks(
    *,
    records: dict[str, list[dict[str, Any]]],
    sync: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build the minimal Phase 1 per-source-sample validity contract.

    Sync threshold failures and explicit record validity are preserved as
    independent reason codes. No sample is removed or relabelled as an action.
    """
    masks: dict[str, dict[str, Any]] = {}
    stream_ids = set(sync.get("streams", {})) | set(records)
    for stream_id in sorted(stream_ids):
        mapping = sync.get("streams", {}).get(stream_id, {}).get("mapping", [])
        rows = records.get(stream_id, [])
        sample_count = max(len(mapping), len(rows))
        samples: list[ValiditySample] = []
        for index in range(sample_count):
            reasons: list[str] = []
            timestamp: int | None = None
            if index < len(mapping):
                timestamp = mapping[index].get("source_timestamp_ns")
                if not mapping[index].get("valid", False):
                    reasons.append("SYNC_DELTA_EXCEEDED")
            if index < len(rows):
                timestamp = rows[index].get("source_timestamp_ns", timestamp)
                explicit_valid = rows[index].get("valid")
                if explicit_valid is None:
                    explicit_valid = rows[index].get("data", {}).get("valid")
                if explicit_valid is False:
                    reasons.append("SOURCE_MARKED_INVALID")
            samples.append(
                ValiditySample(
                    source_timestamp_ns=timestamp,
                    valid=not reasons,
                    reason_codes=tuple(reasons),
                )
            )
        mask = StreamValidityMask(
            stream_id=stream_id,
            mask_version="0.1.0",
            samples=tuple(samples),
        )
        masks[stream_id] = asdict(mask)
    return masks
