from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from embody_data.errors import EmbodyDataError
from embody_data.platform.catalog import JsonCatalog
from embody_data.platform.models import ProjectRecord, RecordingRecord, RunRecord
from embody_data.platform.sources import resolve_source_adapter


class PlatformService:
    def __init__(self, root: Path):
        self.root = root
        self.catalog = JsonCatalog(root / "catalog")

    def create_project(self, name: str, *, project_id: str | None = None) -> dict[str, Any]:
        identity = project_id or f"project-{uuid4().hex[:12]}"
        _validate_id(identity)
        record = ProjectRecord(identity, name, _now())
        self.catalog.put("projects", identity, record.to_dict())
        return record.to_dict()

    def register_recording(
        self,
        project_id: str,
        source: Path,
        *,
        adapter_name: str,
        recording_id: str | None = None,
    ) -> dict[str, Any]:
        self.catalog.get("projects", project_id)
        adapter = resolve_source_adapter(adapter_name)
        if not adapter.probe(source):
            raise EmbodyDataError(
                "source_probe_failed",
                "Source does not satisfy the selected adapter contract.",
                {"adapter": adapter_name, "source": str(source)},
            )
        description = adapter.describe(source)
        identity = recording_id or f"recording-{uuid4().hex[:12]}"
        _validate_id(identity)
        source_identity = str(description.get("source_identity") or description.get("sha256"))
        record = RecordingRecord(
            identity,
            project_id,
            adapter_name,
            str(source.resolve()),
            str(description.get("collection_mode", "profile_resolved_during_processing")),
            str(description.get("semantic_evidence", "profile_resolved_during_processing")),
            _now(),
            source_identity,
        )
        value = record.to_dict()
        value["source_inventory"] = description
        self.catalog.put("recordings", identity, value)
        return value

    def run(
        self, recording_id: str, *, config: dict[str, Any] | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        recording = self.catalog.get("recordings", recording_id)
        identity = run_id or f"run-{uuid4().hex[:12]}"
        _validate_id(identity)
        output = (
            self.root
            / "projects"
            / recording["project_id"]
            / "recordings"
            / recording_id
            / "runs"
            / identity
        )
        source_path = Path(recording["source_path"]).resolve()
        if output.resolve() == source_path or output.resolve().is_relative_to(source_path):
            raise EmbodyDataError(
                "unsafe_output_path",
                "Processing output must be outside the immutable raw source.",
                {"source": str(source_path), "output": str(output.resolve())},
            )
        record = RunRecord(
            identity,
            recording["project_id"],
            recording_id,
            "running",
            str(output.resolve()),
            _now(),
            config=dict(config or {}),
        )
        self.catalog.put("runs", identity, record.to_dict())
        try:
            adapter = resolve_source_adapter(recording["source_adapter"])
            manifest = adapter.process(Path(recording["source_path"]), output, record.config)
            record.state = "succeeded"
            record.finished_at = _now()
            record.manifest_path = str(output / "metadata" / "processed_manifest.json")
            value = record.to_dict()
            value["result"] = {
                "collection_mode": manifest["collection_mode"],
                "stream_count": len(manifest["streams"]),
                "qc_path": str(output / manifest["qc_path"]),
            }
            self.catalog.put("runs", identity, value)
            return value
        except Exception as exc:
            record.state = "failed"
            record.finished_at = _now()
            record.error = exc.to_dict() if isinstance(exc, EmbodyDataError) else {
                "code": "unexpected_error", "message": str(exc)
            }
            self.catalog.put("runs", identity, record.to_dict())
            raise

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.catalog.get("runs", run_id)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
        raise EmbodyDataError(
            "invalid_identity",
            "Identifiers must be 1-80 safe filename characters.",
            {"identity": value},
        )
