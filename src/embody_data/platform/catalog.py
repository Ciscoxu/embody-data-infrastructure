from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


class JsonCatalog:
    """Small local catalog; processing artifacts remain the authoritative outputs."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, kind: str, identity: str, value: dict[str, Any]) -> None:
        path = self.root / kind / f"{identity}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def get(self, kind: str, identity: str) -> dict[str, Any]:
        value = json.loads(
            (self.root / kind / f"{identity}.json").read_text(encoding="utf-8")
        )
        if not isinstance(value, dict):
            raise ValueError(f"Catalog record must be a JSON object: {kind}/{identity}")
        return cast(dict[str, Any], value)

    def list(self, kind: str) -> list[dict[str, Any]]:
        directory = self.root / kind
        if not directory.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        ]
