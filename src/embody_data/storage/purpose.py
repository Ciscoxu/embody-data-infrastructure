from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class PurposeRunLayout:
    """Local-only layout for one immutable purpose projection."""

    root: Path

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def validity_masks(self) -> Path:
        return self.root / "validity_masks"

    @property
    def manifest(self) -> Path:
        return self.root / "purpose_manifest.json"

    @property
    def qc(self) -> Path:
        return self.root / "purpose_qc.json"

    @property
    def status(self) -> Path:
        return self.root / "purpose_status.json"

    @property
    def provenance(self) -> Path:
        return self.root / "provenance.json"

    def required_directories(self) -> tuple[Path, ...]:
        return self.artifacts, self.validity_masks


class PurposeReader:
    """Read a purpose run without importing raw-format or vendor decoders."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = self._read(root / "purpose_manifest.json")

    def qc(self) -> dict[str, Any]:
        return self._read(self.root / self.manifest["qc_path"])

    def status(self) -> dict[str, Any]:
        return self._read(self.root / self.manifest["status_path"])

    def provenance(self) -> dict[str, Any]:
        return self._read(self.root / self.manifest["provenance_path"])

    def artifact_paths(self) -> list[Path]:
        return [self.root / item["path"] for item in self.manifest["artifacts"]]

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
