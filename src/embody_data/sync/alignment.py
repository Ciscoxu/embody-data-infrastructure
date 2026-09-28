from __future__ import annotations

import bisect
import math
from typing import Any


def synchronize(
    timestamps: dict[str, list[int]],
    *,
    reference_stream: str | None = None,
    max_delta_ns: int = 50_000_000,
) -> dict[str, Any]:
    if not timestamps:
        return {"reference_stream": None, "policy": "nearest", "streams": {}}
    if reference_stream not in timestamps:
        reference_stream = next(
            (key for key in timestamps if "camera0" in key and "compressed" in key), None
        )
    reference_stream = reference_stream or next(iter(timestamps))
    reference = timestamps[reference_stream]
    streams: dict[str, Any] = {}
    for stream, values in timestamps.items():
        mapping: list[dict[str, Any]] = []
        errors: list[int] = []
        for source in values:
            index = _nearest(reference, source)
            error = abs(reference[index] - source) if index is not None else None
            valid = error is not None and error <= max_delta_ns
            mapping.append(
                {
                    "source_timestamp_ns": source,
                    "reference_timestamp_ns": reference[index] if index is not None else None,
                    "reference_index": index,
                    "error_ns": error,
                    "valid": valid,
                }
            )
            if error is not None:
                errors.append(error)
        gaps = [right - left for left, right in zip(values, values[1:], strict=False)]
        positive_gaps = [gap for gap in gaps if gap > 0]
        median_gap = sorted(positive_gaps)[len(positive_gaps) // 2] if positive_gaps else None
        streams[stream] = {
            "mapping": mapping,
            "coverage": sum(item["valid"] for item in mapping) / len(mapping) if mapping else 0.0,
            "error_ns": _distribution(errors),
            "duplicates": len(values) - len(set(values)),
            "non_monotonic": sum(
                right < left for left, right in zip(values, values[1:], strict=False)
            ),
            "gap_ns": _distribution(positive_gaps),
            "estimated_frequency_hz": 1e9 / median_gap if median_gap else 0.0,
        }
    return {
        "reference_stream": reference_stream,
        "reference_clock_domain": "preserved_source_clock",
        "policy": "nearest",
        "max_delta_ns": max_delta_ns,
        "interpolation": "none",
        "streams": streams,
    }


def _nearest(values: list[int], target: int) -> int | None:
    if not values:
        return None
    index = bisect.bisect_left(values, target)
    choices = [candidate for candidate in (index - 1, index) if 0 <= candidate < len(values)]
    return min(choices, key=lambda candidate: abs(values[candidate] - target))


def _distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "median": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
        "max": ordered[-1],
    }
