import json

from embody_data.cli.main import main
from embody_data.storage import ProcessedReader
from tests.fixtures.genrobot_fixture import write_genrobot_fixture


def test_synthetic_protobuf_mcap_runs_end_to_end(tmp_path, capsys):
    raw = write_genrobot_fixture(tmp_path / "fixture.mcap")
    inspect_dir = tmp_path / "inspect"
    processed = tmp_path / "processed"

    assert main(["inspect", str(raw), "--output", str(inspect_dir)]) == 0
    inspect_response = json.loads(capsys.readouterr().out)
    assert inspect_response["item_count"] == 5
    assert (inspect_dir / "raw_manifest.json").is_file()
    topic_summary = json.loads((inspect_dir / "topic_summary.json").read_text(encoding="utf-8"))
    assert topic_summary["topics"][0]["channel_id"] > 0

    assert main(["process", str(raw), "--output", str(processed)]) == 0
    process_response = json.loads(capsys.readouterr().out)
    assert process_response["stream_count"] == 5

    manifest = json.loads(
        (processed / "metadata" / "processed_manifest.json").read_text(encoding="utf-8")
    )
    qc = json.loads((processed / "qc" / "qc_report.json").read_text(encoding="utf-8"))
    mapping = json.loads(
        (processed / "metadata" / "timestamp_mapping.json").read_text(encoding="utf-8")
    )
    assert manifest["collection_mode"] == "human_wearable"
    assert manifest["source"]["container"] == "mcap"
    assert manifest["source"]["encoding"] == "protobuf"
    assert manifest["trajectory_semantics"]["eef_pose"] == "observed_device_pose"
    assert manifest["trajectory_semantics"]["action"] == "not_emitted"
    assert manifest["unprocessed_topics"] == []
    assert qc["verdict"] == "warn"
    assert mapping["reference_stream"].endswith("camera0__compressed")
    assert mapping["streams"][mapping["reference_stream"]]["estimated_frequency_hz"] > 0

    reader = ProcessedReader(processed)
    pose_id = next(stream for stream in reader.stream_ids() if stream.endswith("vio__eef_pose"))
    record = next(reader.iter_stream(pose_id))
    assert record["data"]["quaternion_xyzw"] == [0.0, 0.0, 0.0, 1.0]
