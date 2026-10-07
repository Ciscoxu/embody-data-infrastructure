import json

import pytest

from embody_data.errors import EmbodyDataError
from embody_data.platform.sources import registered_source_adapters, resolve_source_adapter


def test_platform_reserves_future_source_paths_without_claiming_support():
    adapters = {item["name"]: item for item in registered_source_adapters()}

    assert adapters["mcap"]["implemented"] is True
    assert adapters["folder_bundle_v1"]["implemented"] is True
    assert adapters["rosbag"]["implemented"] is False
    assert adapters["live_capture"]["implemented"] is False
    assert adapters["vendor_private"]["implemented"] is False
    assert adapters["lerobot"]["implemented"] is False
    assert adapters["rlds"]["implemented"] is False

    with pytest.raises(EmbodyDataError) as caught:
        resolve_source_adapter("rosbag")
    assert caught.value.code == "source_adapter_not_implemented"


def test_folder_bundle_probe_requires_recording_contract(tmp_path):
    adapter = resolve_source_adapter("folder_bundle_v1")
    assert adapter.probe(tmp_path) is False
    (tmp_path / "recording.json").write_text(json.dumps({}), encoding="utf-8")
    assert adapter.probe(tmp_path) is True


def test_invalid_bundle_contract_is_structured(tmp_path):
    from embody_data.decode import DecodeRequest
    from embody_data.decode.folder_bundle import decode_folder_bundle

    (tmp_path / "recording.json").write_text(
        json.dumps({"collection_mode": "human_wearable", "semantic_evidence": "human"}),
        encoding="utf-8",
    )
    with pytest.raises(EmbodyDataError) as caught:
        decode_folder_bundle(
            DecodeRequest(tmp_path, tmp_path / "streams", tmp_path / "assets")
        )
    assert caught.value.code == "bundle_contract_unsupported"


def test_human_wearable_cannot_self_declare_robot_execution(tmp_path):
    from embody_data.decode import DecodeRequest
    from embody_data.decode.folder_bundle import decode_folder_bundle

    (tmp_path / "recording.json").write_text(
        json.dumps(
            {
                "contract_version": "folder_bundle_v1",
                "collection_mode": "human_wearable",
                "semantic_evidence": "Human wore the capture device.",
                "stream_semantics": {"pose": "robot_executed_action"},
                "stream_semantic_evidence": {"pose": "Unverified user declaration."},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pose.csv").write_text(
        "timestamp_ns,tx,ty,tz,qx,qy,qz,qw\n1,0,0,0,0,0,0,1\n",
        encoding="utf-8",
    )
    with pytest.raises(EmbodyDataError) as caught:
        decode_folder_bundle(
            DecodeRequest(tmp_path, tmp_path / "streams", tmp_path / "assets")
        )
    assert caught.value.code == "semantic_role_incompatible"
