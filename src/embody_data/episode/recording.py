from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def whole_recording_episode(
    source: Path, timestamps: dict[str, list[int]], descriptors: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    all_times = [value for values in timestamps.values() for value in values]
    identity = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    devices = sorted(
        {
            "robot0" if "robot0" in descriptor["source_fields"]["topic"] else "robot1"
            for descriptor in descriptors.values()
        }
    )
    return {
        "episode_id": f"recording-{identity}",
        "source_recording": str(source.resolve()),
        "task_directory": source.parent.name,
        "collection_mode": "human_wearable",
        "collection_devices": devices,
        "start_timestamp_ns": min(all_times) if all_times else None,
        "end_timestamp_ns": max(all_times) if all_times else None,
        "boundary_strategy": "whole_recording",
        "boundary_assumption": "No reliable event boundary is available in the MVP source profile.",
        "execution_success": "unknown",
    }
