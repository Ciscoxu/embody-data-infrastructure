import json

import pytest

from embody_data.config import load_config
from embody_data.errors import EmbodyDataError


def test_load_json_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"recording_id": "demo"}), encoding="utf-8")
    assert load_config(path)["recording_id"] == "demo"


def test_reject_non_object_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(EmbodyDataError, match="Top-level"):
        load_config(path)
