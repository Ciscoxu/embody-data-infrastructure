from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast


class ProcessedReader:
    """Read normalized processed data without importing MCAP or vendor decoders."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads(
            (root / "metadata" / "processed_manifest.json").read_text(encoding="utf-8")
        )

    def stream_ids(self) -> list[str]:
        return sorted(self.manifest["streams"])

    def iter_stream(self, stream_id: str) -> Iterator[dict[str, Any]]:
        relative = self.manifest["streams"][stream_id]["path"]
        with (self.root / relative).open(encoding="utf-8") as handle:
            for line in handle:
                yield json.loads(line)

    def episode(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            json.loads((self.root / self.manifest["episode_path"]).read_text(encoding="utf-8")),
        )
