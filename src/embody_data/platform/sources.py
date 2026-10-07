from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from embody_data.errors import EmbodyDataError
from embody_data.processing import process_recording


class SourceAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def future_interface(self) -> bool: ...

    def probe(self, source: Path) -> bool: ...

    def describe(self, source: Path) -> dict[str, Any]: ...

    def process(self, source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]: ...


_SOURCES: dict[str, SourceAdapter] = {}


def register_source_adapter(adapter: SourceAdapter) -> None:
    if adapter.name in _SOURCES:
        raise ValueError(f"Source adapter already registered: {adapter.name}")
    _SOURCES[adapter.name] = adapter


def resolve_source_adapter(name: str) -> SourceAdapter:
    try:
        adapter = _SOURCES[name]
    except KeyError as exc:
        raise EmbodyDataError(
            "source_adapter_not_found", "Source adapter is not registered.", {"adapter": name}
        ) from exc
    if adapter.future_interface:
        raise EmbodyDataError(
            "source_adapter_not_implemented",
            "The source path is reserved but not implemented in this demo.",
            {"adapter": name},
        )
    return adapter


def registered_source_adapters() -> tuple[dict[str, Any], ...]:
    return tuple(
        {"name": item.name, "version": item.version, "implemented": not item.future_interface}
        for item in sorted(_SOURCES.values(), key=lambda value: value.name)
    )


@dataclass(frozen=True, slots=True)
class McapSourceAdapter:
    name: str = "mcap"
    version: str = "0.1.0"
    future_interface: bool = False

    def probe(self, source: Path) -> bool:
        if not source.is_file():
            return False
        try:
            with source.open("rb") as handle:
                return handle.read(8) == b"\x89MCAP0\r\n"
        except OSError:
            return False

    def describe(self, source: Path) -> dict[str, Any]:
        return {"adapter": self.name, "path": str(source.resolve()), "sha256": _file_hash(source)}

    def process(self, source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
        return process_recording(source, output_dir, config)


@dataclass(frozen=True, slots=True)
class FolderBundleSourceAdapter:
    name: str = "folder_bundle_v1"
    version: str = "0.1.0"
    future_interface: bool = False

    def probe(self, source: Path) -> bool:
        return source.is_dir() and (source / "recording.json").is_file()

    def describe(self, source: Path) -> dict[str, Any]:
        metadata = json.loads((source / "recording.json").read_text(encoding="utf-8"))
        files = [path for path in source.iterdir() if path.is_file()]
        return {
            "adapter": self.name,
            "path": str(source.resolve()),
            "collection_mode": metadata.get("collection_mode", "unknown"),
            "semantic_evidence": metadata.get("semantic_evidence", ""),
            "files": [
                {"path": path.name, "size_bytes": path.stat().st_size, "sha256": _file_hash(path)}
                for path in sorted(files)
            ],
            "source_identity": _bundle_hash(files),
        }

    def process(self, source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
        from embody_data.platform.folder_processing import process_folder_bundle

        return process_folder_bundle(source, output_dir, config)


@dataclass(frozen=True, slots=True)
class FutureSourceAdapter:
    name: str
    version: str = "reserved-v1"
    future_interface: bool = True

    def probe(self, source: Path) -> bool:
        return False

    def describe(self, source: Path) -> dict[str, Any]:
        raise NotImplementedError

    def process(self, source: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_hash(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.name.encode())
        digest.update(_file_hash(path).encode())
    return digest.hexdigest()


register_source_adapter(McapSourceAdapter())
register_source_adapter(FolderBundleSourceAdapter())
for _future_name in ("rosbag", "live_capture", "vendor_private", "lerobot", "rlds"):
    register_source_adapter(FutureSourceAdapter(_future_name))
