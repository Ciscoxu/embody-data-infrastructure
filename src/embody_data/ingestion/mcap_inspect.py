from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from embody_data.decode.mcap import header_fields, iter_decoded
from embody_data.errors import EmbodyDataError
from embody_data.ingestion.base import register_inspector
from embody_data.metadata.models import (
    ClockEvidence,
    FileRecord,
    RightsMetadata,
    SourceInventory,
    SourceStreamInventory,
)
from embody_data.metadata.source_profiles import (
    collection_mode_decision,
    decide_profile,
    discover_profile_candidates,
    resolve_source_profile,
)

_MCAP_MAGIC = b"\x89MCAP0\r\n"


def inspect_mcap(path: Path, output_dir: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EmbodyDataError("raw_not_found", f"MCAP input does not exist: {path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmbodyDataError("output_not_empty", f"Refusing to overwrite: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "message_count": 0,
            "first_log_time_ns": None,
            "last_log_time_ns": None,
            "first_publish_time_ns": None,
            "last_publish_time_ns": None,
            "first_header_time_ns": None,
            "last_header_time_ns": None,
            "log_time_monotonic": True,
            "publish_time_monotonic": True,
            "header_time_monotonic": True,
            "duplicate_header_timestamps": 0,
            "clock_domains": ["mcap_log", "mcap_publish", "protobuf_header_unknown"],
        }
    )
    schemas: dict[str, dict[str, Any]] = {}
    previous: dict[str, dict[str, int | None]] = defaultdict(dict)
    frame_candidates: set[str] = set()
    global_start: int | None = None
    global_end: int | None = None
    try:
        for item in iter_decoded(path):
            row = stats[item.topic]
            header_ns, _, _ = header_fields(item.decoded)
            _, _, frame_id = header_fields(item.decoded)
            if frame_id != "unknown":
                frame_candidates.add(frame_id)
            row["message_count"] += 1
            _update_time(row, previous[item.topic], "log", item.log_time_ns)
            _update_time(row, previous[item.topic], "publish", item.publish_time_ns)
            if header_ns is not None:
                _update_time(row, previous[item.topic], "header", header_ns)
            global_start = (
                item.log_time_ns if global_start is None else min(global_start, item.log_time_ns)
            )
            global_end = (
                item.log_time_ns if global_end is None else max(global_end, item.log_time_ns)
            )
            schemas[item.topic] = {
                "channel_id": item.channel_id,
                "schema_id": item.schema_id,
                "schema_name": item.schema_name,
                "schema_encoding": item.schema_encoding,
                "message_encoding": item.message_encoding,
            }
    except Exception as exc:
        if isinstance(exc, EmbodyDataError):
            raise
        raise EmbodyDataError(
            "mcap_decode_error", "Unable to inspect MCAP messages.", {"reason": str(exc)}
        ) from exc
    topics: list[dict[str, Any]] = []
    duration_ns = 0 if global_start is None or global_end is None else global_end - global_start
    for topic, row in sorted(stats.items()):
        span = (row["last_log_time_ns"] or 0) - (row["first_log_time_ns"] or 0)
        row["frequency_hz"] = 0.0 if span <= 0 else (row["message_count"] - 1) * 1e9 / span
        topics.append({"topic": topic, **schemas[topic], **row})
    sha256 = _sha256(path)
    candidates = discover_profile_candidates(
        container="mcap",
        schema_encodings={schema["schema_encoding"] for schema in schemas.values()},
        streams=set(stats),
    )
    profile_decision = decide_profile(candidates)
    selected_profile = (
        resolve_source_profile(profile_decision.selected_profile)
        if profile_decision.selected_profile is not None
        else None
    )
    collection_mode = (
        collection_mode_decision(selected_profile) if selected_profile is not None else None
    )
    inventory = SourceInventory(
        inventory_version="0.1.0",
        source_object_identity=sha256,
        source_path=str(path.resolve()),
        files=(FileRecord(path.name, path.stat().st_size, sha256, "readable"),),
        container="mcap",
        schemas=tuple(sorted({schema["schema_name"] for schema in schemas.values()})),
        streams=tuple(
            SourceStreamInventory(
                stream_id=topic["topic"],
                schema_name=topic["schema_name"],
                schema_encoding=topic["schema_encoding"],
                message_encoding=topic["message_encoding"],
                message_count=topic["message_count"],
                first_log_time_ns=topic["first_log_time_ns"],
                last_log_time_ns=topic["last_log_time_ns"],
            )
            for topic in topics
        ),
        timestamp_candidates=("mcap_log", "mcap_publish", "protobuf_header"),
        clock_evidence=(
            ClockEvidence("mcap_log", "log_time", "mcap_message"),
            ClockEvidence("mcap_publish", "publish_time", "mcap_message"),
            ClockEvidence("protobuf_header_unknown", "header_time", "decoded_message_header"),
        ),
        calibration_candidates=tuple(
            sorted(topic for topic in stats if topic.endswith("/camera_info"))
        ),
        frame_candidates=tuple(sorted(frame_candidates)),
        profile_decision=profile_decision,
        collection_mode=collection_mode,
        rights=(
            RightsMetadata(
                consent=selected_profile.consent,
                license=selected_profile.license,
                privacy_redaction=selected_profile.privacy_redaction,
                operator_pseudonym=selected_profile.operator_pseudonym,
                permitted_use=selected_profile.permitted_use,
            )
            if selected_profile is not None
            else RightsMetadata()
        ),
    )
    result = {
        "manifest_version": "0.1.0",
        "source_type": profile_decision.selected_profile or "unknown_mcap",
        "source_path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "duration_ns": duration_ns,
        "collection_mode": collection_mode.mode if collection_mode is not None else "unknown",
        "semantic_evidence": (
            selected_profile.semantic_evidence if selected_profile is not None else "unknown"
        ),
        "profile_decision": profile_decision.to_dict(),
        "collection_mode_decision": inventory.to_dict()["collection_mode"],
        "topics": topics,
    }
    raw_manifest = {
        "manifest_version": "0.1.0",
        "source_id": f"{profile_decision.selected_profile or 'mcap'}-{sha256[:12]}",
        "recording_id": path.stem,
        "source_path": str(path.resolve()),
        "files": [
            {
                "relative_path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256,
                "read_status": "readable",
                "error": None,
            }
        ],
        "metadata": (
            selected_profile.to_dict()
            if selected_profile is not None
            else {
                "source_type": "unknown_mcap",
                "collection_mode": "unknown",
                "profile_status": profile_decision.status,
            }
        ),
    }
    (output_dir / "raw_manifest.json").write_text(
        json.dumps(raw_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "checksum_manifest.json").write_text(
        json.dumps({"algorithm": "sha256", "files": {path.name: sha256}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "topic_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "source_inventory.json").write_text(
        json.dumps(inventory.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "profile_decision.json").write_text(
        json.dumps(profile_decision.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "ingestion_status.json").write_text(
        json.dumps({"operation": "mcap_inspect", "state": "succeeded"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


class McapInspectionAdapter:
    name = "mcap"
    container = "mcap"

    def matches(self, source: Path) -> bool:
        if not source.is_file():
            return False
        try:
            with source.open("rb") as handle:
                return handle.read(len(_MCAP_MAGIC)) == _MCAP_MAGIC
        except OSError:
            return False

    def inspect(self, source: Path, output_dir: Path) -> dict[str, Any]:
        return inspect_mcap(source, output_dir)


MCAP_INSPECTOR = McapInspectionAdapter()
register_inspector(MCAP_INSPECTOR)


def _update_time(
    row: dict[str, Any], previous: dict[str, int | None], kind: str, value: int
) -> None:
    first_key = f"first_{kind}_time_ns"
    last_key = f"last_{kind}_time_ns"
    monotonic_key = f"{kind}_time_monotonic"
    prior = previous.get(kind)
    if row[first_key] is None:
        row[first_key] = value
    if prior is not None and value < prior:
        row[monotonic_key] = False
    if kind == "header" and prior == value:
        row["duplicate_header_timestamps"] += 1
    row[last_key] = value
    previous[kind] = value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
