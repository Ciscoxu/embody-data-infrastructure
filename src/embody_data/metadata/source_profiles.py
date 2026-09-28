from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from embody_data.metadata.models import (
    ClassificationEvidence,
    CollectionMode,
    CollectionModeDecision,
    DecisionConfidence,
    ProfileCandidate,
    ProfileDecision,
)


@dataclass(frozen=True, slots=True)
class SourceProfile:
    source_type: str
    container: str
    encoding: str
    dataset_repo_id: str
    collection_mode: CollectionMode
    semantic_evidence: str
    trajectory_semantics: dict[str, str]
    semantic_assumptions: tuple[str, ...]
    license: str
    gated_access: bool
    consent: str = "unknown"
    privacy_redaction: str = "unknown"
    operator_pseudonym: str = "unknown"
    permitted_use: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


GENROBOT_REALOMIN = SourceProfile(
    source_type="genrobot_realomin_mcap",
    container="mcap",
    encoding="protobuf",
    dataset_repo_id="genrobot2025/10Kh-RealOmin-OpenData",
    collection_mode="human_wearable",
    semantic_evidence=(
        "Gen DAS is a human-operated dual-hand/gripper capture device; no synchronized "
        "robot execution feedback is established by the source profile."
    ),
    trajectory_semantics={
        "eef_pose": "observed_device_pose",
        "magnetic_encoder": "observed_human_motion",
        "action": "not_emitted",
    },
    semantic_assumptions=(
        "Gen DAS pose is observed device trajectory, not robot action.",
        "IMU linear acceleration remains g_force per vendor documentation.",
        "RobotInfo/SystemInfo topic names do not establish synchronized robot execution.",
    ),
    license="CC-BY-SA-4.0",
    gated_access=True,
)


ProfileMatcher = Callable[[str, set[str], set[str]], ProfileCandidate | None]
_SOURCE_PROFILES: dict[str, SourceProfile] = {}
_PROFILE_MATCHERS: list[ProfileMatcher] = []


def register_source_profile(profile: SourceProfile, matcher: ProfileMatcher) -> None:
    if profile.source_type in _SOURCE_PROFILES:
        raise ValueError(f"Source profile is already registered: {profile.source_type}")
    _SOURCE_PROFILES[profile.source_type] = profile
    _PROFILE_MATCHERS.append(matcher)


def resolve_source_profile(source_type: str) -> SourceProfile:
    try:
        return _SOURCE_PROFILES[source_type]
    except KeyError as exc:
        raise KeyError(f"Source profile is not registered: {source_type}") from exc


def discover_profile_candidates(
    *, container: str, schema_encodings: set[str], streams: set[str]
) -> tuple[ProfileCandidate, ...]:
    candidates = (
        matcher(container, schema_encodings, streams) for matcher in _PROFILE_MATCHERS
    )
    return tuple(candidate for candidate in candidates if candidate is not None)


def decide_profile(
    candidates: tuple[ProfileCandidate, ...], *, requested_profile: str | None = None
) -> ProfileDecision:
    """Resolve a profile without silently choosing between equally strong evidence."""
    if requested_profile is not None:
        matching = tuple(
            candidate for candidate in candidates if candidate.profile == requested_profile
        )
        if len(matching) == 1:
            evidence = ClassificationEvidence(
                source="user_source_hint",
                detail=f"Explicit source profile requested: {requested_profile}",
                confidence="high",
            )
            return ProfileDecision("confirmed", requested_profile, candidates, (evidence,))
        return ProfileDecision(
            "unknown",
            None,
            candidates,
            (
                ClassificationEvidence(
                    source="user_source_hint",
                    detail=(
                        "Requested profile is not supported by discovered evidence: "
                        f"{requested_profile}"
                    ),
                    confidence="low",
                ),
            ),
        )
    if not candidates:
        return ProfileDecision("unknown", None, ())
    rank = {"low": 0, "medium": 1, "high": 2}
    strongest_rank = max(rank[candidate.confidence] for candidate in candidates)
    strongest = tuple(
        candidate for candidate in candidates if rank[candidate.confidence] == strongest_rank
    )
    if len(strongest) != 1:
        return ProfileDecision("ambiguous", None, candidates)
    return ProfileDecision("confirmed", strongest[0].profile, candidates)


def genrobot_profile_candidate(
    *, container: str, schema_encodings: set[str], streams: set[str]
) -> ProfileCandidate | None:
    """Return a RealOmin candidate based on container/schema/topic content, not filenames."""
    matching_streams = {
        stream
        for stream in streams
        if stream.startswith(("/robot0/sensor/", "/robot1/sensor/", "/robot0/vio/", "/robot1/vio/"))
    }
    protobuf_evidence = any("protobuf" in encoding.lower() for encoding in schema_encodings)
    if container != "mcap" or not protobuf_evidence or not matching_streams:
        return None
    confidence: DecisionConfidence = "high" if len(matching_streams) >= 2 else "medium"
    evidence = ClassificationEvidence(
        source="content_fingerprint",
        detail=(
            f"MCAP contains embedded Protobuf and {len(matching_streams)} "
            "GenRobot-profile stream(s)."
        ),
        confidence=confidence,
    )
    return ProfileCandidate(GENROBOT_REALOMIN.source_type, confidence, (evidence,))


def collection_mode_decision(profile: SourceProfile) -> CollectionModeDecision:
    evidence = ClassificationEvidence(
        source="documented_source_profile",
        detail=profile.semantic_evidence,
        confidence="high",
    )
    return CollectionModeDecision(profile.collection_mode, "high", (evidence,))


def genrobot_collection_mode_decision() -> CollectionModeDecision:
    """Backward-compatible wrapper for the initial source profile."""
    return collection_mode_decision(GENROBOT_REALOMIN)


register_source_profile(
    GENROBOT_REALOMIN,
    lambda container, schema_encodings, streams: genrobot_profile_candidate(
        container=container,
        schema_encodings=schema_encodings,
        streams=streams,
    ),
)
