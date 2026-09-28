from pathlib import Path

import pytest

from embody_data.decode import (
    AdapterKey,
    DecodeRequest,
    dispatch_decode,
    registered_adapter_keys,
)
from embody_data.decode.genrobot import decode_recording
from embody_data.errors import EmbodyDataError
from embody_data.metadata.source_profiles import GENROBOT_REALOMIN
from tests.fixtures.genrobot_fixture import write_genrobot_fixture

GENROBOT_KEY = AdapterKey("mcap", "protobuf", GENROBOT_REALOMIN.source_type)


def test_genrobot_adapter_is_registered_and_dispatches_selective_decode(tmp_path: Path):
    raw = write_genrobot_fixture(tmp_path / "fixture.mcap")
    start = 1_700_000_000_033_000_000
    result = dispatch_decode(
        GENROBOT_KEY,
        DecodeRequest(
            source=raw,
            streams_dir=tmp_path / "streams",
            assets_dir=tmp_path / "assets",
            streams=frozenset({"robot0__vio__eef_pose"}),
            start=start,
            end=start + 66_000_000,
        ),
    )

    assert GENROBOT_KEY in registered_adapter_keys()
    assert set(result.descriptors) == {"robot0__vio__eef_pose"}
    assert result.timestamps["robot0__vio__eef_pose"] == [start, start + 33_000_000]


def test_missing_adapter_is_structured_error(tmp_path: Path):
    with pytest.raises(EmbodyDataError, match="No decoder adapter") as caught:
        dispatch_decode(
            AdapterKey("hdf5", "table", "unknown"),
            DecodeRequest(tmp_path / "raw.h5", tmp_path / "streams", tmp_path / "assets"),
        )

    assert caught.value.code == "decoder_not_found"


def test_decode_failure_is_preserved_without_aborting_other_streams(tmp_path: Path):
    raw = write_genrobot_fixture(tmp_path / "bad.mcap", bad_gripper=True)
    result = decode_recording(raw, tmp_path / "streams", tmp_path / "assets")

    assert len(result.decode_failures) == 3
    assert {failure["topic"] for failure in result.decode_failures} == {
        "/robot0/sensor/magnetic_encoder"
    }
    assert "robot0__vio__eef_pose" in result.descriptors
