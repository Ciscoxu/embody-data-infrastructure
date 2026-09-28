import json

from embody_data.cli.main import main


def test_inspect_writes_structured_manifests(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "imu.csv").write_text("timestamp,ax\n0,1\n", encoding="utf-8")
    output = tmp_path / "manifest"

    assert main(["inspect", str(raw), "--output", str(output)]) == 0
    response = json.loads(capsys.readouterr().out)
    manifest = json.loads((output / "raw_manifest.json").read_text(encoding="utf-8"))

    assert response["status"] == "succeeded"
    assert manifest["files"][0]["relative_path"] == "imu.csv"
    assert (output / "checksum_manifest.json").is_file()
    assert (output / "topic_summary.json").is_file()
    assert (output / "ingestion_status.json").is_file()


def test_process_requires_structured_output_path(tmp_path, capsys):
    assert main(["process", str(tmp_path)]) == 2
    response = json.loads(capsys.readouterr().err)
    assert response["error"]["code"] == "output_required"
