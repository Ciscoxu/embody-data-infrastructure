import json

from embody_data.acquisition import huggingface as acquisition
from embody_data.acquisition.huggingface import RemoteFile, select_files
from embody_data.errors import EmbodyDataError


def test_selection_is_bounded_and_prefers_one_small_leaf():
    files = [
        RemoteFile("task/a/1.mcap", 10, "a"),
        RemoteFile("task/a/2.mcap", 20, "b"),
        RemoteFile("task/b/large.mcap", 1000, "c"),
    ]
    selected = select_files(files, paths=None, max_files=2, max_bytes=100)
    assert [item.path for item in selected] == ["task/a/1.mcap", "task/a/2.mcap"]


def test_blocked_auth_status_is_machine_readable(tmp_path, monkeypatch):
    def blocked(**kwargs):
        raise EmbodyDataError("blocked_auth", "accept conditions")

    monkeypatch.setattr(acquisition, "list_genrobot_files", blocked)
    result = acquisition.acquire_genrobot(tmp_path)
    saved = json.loads((tmp_path / "acquisition_status.json").read_text(encoding="utf-8"))
    assert result["state"] == saved["state"] == "blocked_auth"
    assert "token" not in json.dumps(saved).lower()


def test_acquisition_resolves_relative_output_root(tmp_path, monkeypatch):
    remote = RemoteFile("task/leaf/sample.mcap", 4, "content-id")

    monkeypatch.setattr(
        acquisition,
        "list_genrobot_files",
        lambda **kwargs: ("commit", [remote]),
    )
    monkeypatch.chdir(tmp_path)
    result = acquisition.acquire_genrobot(tmp_path / "relative-root", dry_run=True, max_files=1)

    assert result["state"] == "dry_run"
    assert (tmp_path / "relative-root" / "acquisition_status.json").is_file()
