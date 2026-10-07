from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from embody_data.errors import EmbodyDataError
from embody_data.processing import process_recording

try:
    from embody_data.platform import PlatformService
except ImportError:  # compatibility with checkouts predating the local platform service
    PlatformService = None  # type: ignore[misc, assignment]


class DemoPlatformBridge:
    """Narrow adapter between the HTTP demo and the local platform service."""

    project_id = "project-demo"

    def __init__(self, root: Path):
        self.root = root
        self.service = PlatformService(root) if PlatformService is not None else None
        if self.service is not None:
            try:
                self.service.catalog.get("projects", self.project_id)
            except FileNotFoundError:
                self.service.create_project("Local Demo", project_id=self.project_id)

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = Path(str(payload["source_path"]))
        adapter = str(payload["input_type"])
        if self.service is None:
            return self._fallback_register(source, adapter, payload)
        record = self.service.register_recording(
            self.project_id,
            source,
            adapter_name=adapter,
        )
        declared_mode = str(payload["collection_mode"])
        confirmed_mode = str(record.get("collection_mode", "unknown"))
        record.update(
            {
                "input_type": adapter,
                "declared_collection_mode": declared_mode,
                "collection_mode_matches_source": confirmed_mode
                in {"unknown", "profile_resolved_during_processing", declared_mode},
                "operator_pseudonym": str(payload.get("operator_pseudonym") or "unknown"),
                "device_id": str(payload.get("device_id") or "unknown"),
                "rights": payload["rights"],
            }
        )
        self.service.catalog.put("recordings", record["recording_id"], record)
        return record

    def list_recordings(self) -> list[dict[str, Any]]:
        if self.service is None:
            return self._fallback_list("recordings")
        records = self.service.catalog.list("recordings")
        runs = self.service.catalog.list("runs")
        for record in records:
            record["runs"] = [
                run for run in runs if run["recording_id"] == record["recording_id"]
            ]
        return sorted(records, key=lambda value: value["registered_at"], reverse=True)

    def get_recording(self, recording_id: str) -> dict[str, Any]:
        if self.service is None:
            return self._fallback_get("recordings", recording_id)
        try:
            return self.service.catalog.get("recordings", recording_id)
        except FileNotFoundError as exc:
            raise EmbodyDataError(
                "recording_not_found", f"Unknown recording: {recording_id}"
            ) from exc

    def process(self, recording_id: str) -> dict[str, Any]:
        record = self.get_recording(recording_id)
        if record.get("collection_mode_matches_source") is False:
            raise EmbodyDataError(
                "collection_mode_conflict",
                "Declared collection mode conflicts with source metadata.",
                {
                    "declared": record["declared_collection_mode"],
                    "source": record["collection_mode"],
                },
            )
        if self.service is None:
            return self._fallback_process(record)
        run = self.service.run(
            recording_id,
            config={
                "declared_collection_mode": record["declared_collection_mode"],
                "operator_pseudonym": record.get("operator_pseudonym", "unknown"),
                "device_id": record.get("device_id", "unknown"),
                "rights": record.get("rights", {}),
            },
        )
        return {**run, **read_run_artifacts(Path(run["output_path"]))}

    def get_run(self, run_id: str) -> dict[str, Any]:
        if self.service is None:
            run = self._fallback_get("runs", run_id)
        else:
            try:
                run = self.service.get_run(run_id)
            except FileNotFoundError as exc:
                raise EmbodyDataError("run_not_found", f"Unknown run: {run_id}") from exc
        return {**run, **read_run_artifacts(Path(run["output_path"]))}

    def _fallback_register(
        self, source: Path, adapter: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if adapter != "mcap":
            raise EmbodyDataError(
                "source_adapter_not_implemented",
                "This checkout has no platform adapter for the selected source.",
                {"adapter": adapter},
            )
        from uuid import uuid4

        identity = f"recording-{uuid4().hex[:12]}"
        record = {
            "recording_id": identity,
            "project_id": self.project_id,
            "source_adapter": adapter,
            "input_type": adapter,
            "source_path": str(source.resolve()),
            "collection_mode": "profile_resolved_during_processing",
            "declared_collection_mode": payload["collection_mode"],
            "collection_mode_matches_source": True,
            "registered_at": "fallback",
            "rights": payload["rights"],
        }
        self._fallback_put("recordings", identity, record)
        return record

    def _fallback_process(self, record: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4

        run_id = f"run-{uuid4().hex[:12]}"
        output = self.root / "runs" / run_id
        manifest = process_recording(Path(record["source_path"]), output, {})
        if manifest["collection_mode"] != record["declared_collection_mode"]:
            raise EmbodyDataError(
                "collection_mode_conflict",
                "Declared collection mode conflicts with the confirmed source profile.",
            )
        run = {
            "run_id": run_id,
            "recording_id": record["recording_id"],
            "state": "succeeded",
            "output_path": str(output.resolve()),
        }
        self._fallback_put("runs", run_id, run)
        return {**run, **read_run_artifacts(output)}

    def _fallback_put(self, kind: str, identity: str, value: dict[str, Any]) -> None:
        path = self.root / "fallback_catalog" / kind / f"{identity}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def _fallback_get(self, kind: str, identity: str) -> dict[str, Any]:
        path = self.root / "fallback_catalog" / kind / f"{identity}.json"
        if not path.is_file():
            raise EmbodyDataError(f"{kind[:-1]}_not_found", f"Unknown {kind[:-1]}: {identity}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _fallback_list(self, kind: str) -> list[dict[str, Any]]:
        directory = self.root / "fallback_catalog" / kind
        if not directory.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")
        ]


def read_run_artifacts(output_dir: Path) -> dict[str, Any]:
    return {
        "status": _read_json(output_dir / "metadata" / "processing_status.json"),
        "qc": _read_json(output_dir / "qc" / "qc_report.json"),
        "manifest": _read_json(output_dir / "metadata" / "processed_manifest.json"),
        "declaration": _read_json(output_dir / "metadata" / "recording_declaration.json"),
    }


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
