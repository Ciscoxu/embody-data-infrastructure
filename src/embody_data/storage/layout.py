from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcessedRunLayout:
    root: Path

    @property
    def metadata(self) -> Path:
        return self.root / "metadata"

    @property
    def qc(self) -> Path:
        return self.root / "qc"

    def required_directories(self) -> tuple[Path, ...]:
        return (
            self.root / "data" / "episodes",
            self.root / "data" / "streams",
            self.root / "data" / "derived",
            self.root / "calibration",
            self.metadata,
            self.qc / "validity_masks",
        )
