"""Evolvable Phase 1 general internal representation."""

from embody_data.representation.genrobot import descriptor_for, profile_topic
from embody_data.representation.stream import (
    CollectionMode,
    NormalizedRecord,
    SemanticRole,
    StreamDescriptor,
)

__all__ = [
    "CollectionMode",
    "NormalizedRecord",
    "SemanticRole",
    "StreamDescriptor",
    "descriptor_for",
    "profile_topic",
]
