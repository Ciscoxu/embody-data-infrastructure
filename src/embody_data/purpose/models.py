from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from embody_data.errors import EmbodyDataError


class PurposeKind(StrEnum):
    ARCHIVAL = "archival"
    EXPLORATION = "exploration"
    LEARNING_READINESS = "learning_readiness"
    RETARGETING = "retargeting"
    CONTROL_EVALUATION = "control_evaluation"


@dataclass(frozen=True, slots=True)
class PurposeProfile:
    name: str
    purpose: PurposeKind
    version: str
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PurposeProfile:
        try:
            return cls(
                name=str(value["name"]),
                purpose=PurposeKind(value["purpose"]),
                version=str(value["version"]),
                options=dict(value.get("options", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbodyDataError(
                "invalid_purpose_profile",
                "Purpose profile must declare a valid name, purpose, and version.",
                {"reason": str(exc)},
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PurposeRun:
    run_id: str
    recording_id: str
    profile: PurposeProfile
    normalized_run: str
    normalized_manifest_sha256: str
    selected_streams: list[str]
    selected_episodes: list[str]
    artifacts: list[dict[str, Any]]
    validity_masks: list[dict[str, Any]]
    qc_path: str
    status_path: str
    provenance_path: str
    created_at: str
    manifest_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
