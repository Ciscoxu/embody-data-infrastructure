from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from embody_data.errors import EmbodyDataError


class InspectionAdapter(Protocol):
    name: str
    container: str

    def matches(self, source: Path) -> bool: ...

    def inspect(self, source: Path, output_dir: Path) -> dict[str, Any]: ...


_INSPECTORS: list[InspectionAdapter] = []


def register_inspector(inspector: InspectionAdapter) -> None:
    if any(item.name == inspector.name for item in _INSPECTORS):
        raise ValueError(f"Inspector is already registered: {inspector.name}")
    _INSPECTORS.append(inspector)


def registered_inspectors() -> tuple[str, ...]:
    return tuple(inspector.name for inspector in _INSPECTORS)


def resolve_inspector(source: Path) -> InspectionAdapter:
    matches = tuple(inspector for inspector in _INSPECTORS if inspector.matches(source))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise EmbodyDataError(
            "inspector_not_found",
            "No inspector is registered for the source content.",
            {"source_path": str(source.resolve())},
        )
    raise EmbodyDataError(
        "inspector_ambiguous",
        "Multiple inspectors matched the source content.",
        {"inspectors": [inspector.name for inspector in matches]},
    )


def inspect_recording(source: Path, output_dir: Path) -> dict[str, Any]:
    return resolve_inspector(source).inspect(source, output_dir)
