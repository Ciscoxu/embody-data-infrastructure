from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from embody_data.errors import EmbodyDataError
from embody_data.metadata.models import FileRecord, RawManifest
from embody_data.status import OperationStatus

_CHUNK_SIZE = 1024 * 1024


def inspect_raw(raw_path: Path, output_dir: Path, config: dict[str, Any]) -> RawManifest:
    """Inventory raw data without loading full files into memory."""
    if not raw_path.exists():
        raise EmbodyDataError("raw_not_found", f"Raw input does not exist: {raw_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EmbodyDataError(
            "output_not_empty",
            f"Refusing to overwrite non-empty output directory: {output_dir}",
        )

    status = OperationStatus.started("inspect")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [_inspect_file(path, raw_path) for path in _iter_files(raw_path)]
    identity = _recording_identity(files)
    recording_id = str(config.get("recording_id") or f"recording-{identity[:12]}")
    source_id = str(config.get("source_id") or f"source-{identity[:12]}")
    session = config.get("session_id")
    session_id = str(session) if session is not None else None

    manifest = RawManifest(
        manifest_version="0.1.0",
        source_id=source_id,
        recording_id=recording_id,
        session_id=session_id,
        source_path=str(raw_path.resolve()),
        files=files,
        metadata={
            "source_type": config.get("source_type", "generic-filesystem"),
            "device": config.get("device", "unknown"),
            "protocol_version": config.get("protocol_version", "unknown"),
        },
    )
    failed = [record for record in files if record.read_status != "readable"]
    if failed:
        status.warnings.append(
            {
                "code": "unreadable_files",
                "count": len(failed),
                "files": [f.relative_path for f in failed],
            }
        )
    status.finish(succeeded=True)

    _write_json(output_dir / "raw_manifest.json", manifest.to_dict())
    _write_json(
        output_dir / "topic_summary.json",
        {
            "status": "not_decoded",
            "streams": [],
            "note": "Generic inspection cannot infer topics without a source decoder.",
        },
    )
    _write_json(output_dir / "ingestion_status.json", status.to_dict())
    _write_json(
        output_dir / "checksum_manifest.json",
        {
            "algorithm": "sha256",
            "files": {record.relative_path: record.sha256 for record in files},
        },
    )
    return manifest


def _iter_files(raw_path: Path) -> Iterable[Path]:
    if raw_path.is_file():
        yield raw_path
        return
    yield from sorted(path for path in raw_path.rglob("*") if path.is_file())


def _inspect_file(path: Path, root: Path) -> FileRecord:
    relative_path = path.name if root.is_file() else path.relative_to(root).as_posix()
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                digest.update(chunk)
        return FileRecord(relative_path, path.stat().st_size, digest.hexdigest(), "readable")
    except OSError as exc:
        return FileRecord(relative_path, 0, None, "unreadable", str(exc))


def _recording_identity(files: list[FileRecord]) -> str:
    digest = hashlib.sha256()
    for record in files:
        digest.update(record.relative_path.encode())
        digest.update((record.sha256 or "unreadable").encode())
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
