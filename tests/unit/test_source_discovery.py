import json
from pathlib import Path

from embody_data.ingestion import inspect_mcap, inspect_recording, registered_inspectors
from embody_data.metadata.models import ClassificationEvidence, ProfileCandidate
from embody_data.metadata.source_profiles import (
    GENROBOT_REALOMIN,
    SourceProfile,
    decide_profile,
    discover_profile_candidates,
    genrobot_profile_candidate,
    register_source_profile,
    resolve_source_profile,
)
from tests.fixtures.genrobot_fixture import write_genrobot_fixture


def test_genrobot_profile_uses_content_fingerprint():
    candidate = genrobot_profile_candidate(
        container="mcap",
        schema_encodings={"protobuf"},
        streams={"/robot0/sensor/imu", "/robot0/vio/eef_pose"},
    )

    assert candidate is not None
    decision = decide_profile((candidate,))
    assert decision.status == "confirmed"
    assert decision.selected_profile == GENROBOT_REALOMIN.source_type
    assert decision.candidates[0].evidence[0].source == "content_fingerprint"


def test_unknown_schema_does_not_select_profile():
    candidate = genrobot_profile_candidate(
        container="mcap", schema_encodings={"jsonschema"}, streams={"/robot0/sensor/imu"}
    )

    assert candidate is None
    assert decide_profile(()).status == "unknown"


def test_source_profile_registry_carries_dispatch_and_semantic_contract():
    profile = SourceProfile(
        source_type="fixture_csv_capture",
        container="filesystem",
        encoding="csv",
        dataset_repo_id="not_applicable",
        collection_mode="teleop_device_only",
        semantic_evidence="Fixture contains operator device signals without robot feedback.",
        trajectory_semantics={"device_pose": "observed_device_pose", "action": "not_emitted"},
        semantic_assumptions=("No robot execution feedback is present.",),
        license="unknown",
        gated_access=False,
    )
    evidence = (ClassificationEvidence("fixture", "CSV fixture layout", "high"),)
    register_source_profile(
        profile,
        lambda container, _encodings, _streams: (
            ProfileCandidate(profile.source_type, "high", evidence)
            if container == profile.container
            else None
        ),
    )

    candidates = discover_profile_candidates(
        container="filesystem", schema_encodings={"csv"}, streams={"device_pose"}
    )

    assert decide_profile(candidates).selected_profile == profile.source_type
    assert resolve_source_profile(profile.source_type).encoding == "csv"


def test_equal_profile_evidence_is_ambiguous():
    evidence = (ClassificationEvidence("fixture", "same-strength evidence", "medium"),)
    decision = decide_profile(
        (
            ProfileCandidate("profile_a", "medium", evidence),
            ProfileCandidate("profile_b", "medium", evidence),
        )
    )

    assert decision.status == "ambiguous"
    assert decision.selected_profile is None


def test_mcap_inspect_emits_source_inventory_and_collection_evidence(tmp_path: Path):
    raw = write_genrobot_fixture(tmp_path / "fixture.mcap")
    output = tmp_path / "inspect"

    inspect_mcap(raw, output)

    inventory = json.loads((output / "source_inventory.json").read_text(encoding="utf-8"))
    profile = json.loads((output / "profile_decision.json").read_text(encoding="utf-8"))
    assert inventory["container"] == "mcap"
    assert inventory["source_object_identity"]
    assert inventory["collection_mode"]["mode"] == "human_wearable"
    assert inventory["collection_mode"]["evidence"][0]["source"] == "documented_source_profile"
    assert profile["selected_profile"] == GENROBOT_REALOMIN.source_type


def test_recording_inspector_dispatches_from_content_not_filename(tmp_path: Path):
    raw = write_genrobot_fixture(tmp_path / "recording.bin")
    output = tmp_path / "inspect"

    result = inspect_recording(raw, output)

    assert "mcap" in registered_inspectors()
    assert result["profile_decision"]["selected_profile"] == GENROBOT_REALOMIN.source_type
