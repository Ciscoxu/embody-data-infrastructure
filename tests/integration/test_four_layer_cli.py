import json

from embody_data.cli.main import main
from tests.fixtures.genrobot_fixture import write_genrobot_fixture


def test_cli_runs_discovery_dispatch_layered_qc_and_local_purpose(tmp_path, capsys):
    raw = write_genrobot_fixture(tmp_path / "fixture.mcap")
    processed = tmp_path / "processed"

    assert main(["process", str(raw), "--output", str(processed)]) == 0
    process_response = json.loads(capsys.readouterr().out)
    assert process_response["status"] == "succeeded"

    inspect = processed / "metadata" / "inspect"
    assert (inspect / "source_inventory.json").is_file()
    decision = json.loads((inspect / "profile_decision.json").read_text(encoding="utf-8"))
    assert decision["status"] == "confirmed"
    assert decision["selected_profile"] == "genrobot_realomin_mcap"
    assert (processed / "qc" / "source_qc.json").is_file()
    assert (processed / "qc" / "semantic_qc.json").is_file()
    assert any((processed / "qc" / "validity_masks").iterdir())

    config = tmp_path / "exploration.json"
    config.write_text(
        json.dumps(
            {
                "name": "test_exploration",
                "purpose": "exploration",
                "version": "0.1.0",
                "options": {"preview_stride": 2},
            }
        ),
        encoding="utf-8",
    )
    purpose = tmp_path / "purpose"
    assert main(
        [
            "purpose",
            str(processed),
            "--output",
            str(purpose),
            "--config",
            str(config),
        ]
    ) == 0
    purpose_response = json.loads(capsys.readouterr().out)
    assert purpose_response["purpose"] == "exploration"
    assert purpose_response["artifact_count"] == 2
    manifest = json.loads((purpose / "purpose_manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"]["purpose"] == "exploration"

