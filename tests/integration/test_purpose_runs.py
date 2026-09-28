import hashlib
import json

from embody_data.processing import process_genrobot_mcap
from embody_data.purpose import PurposeKind, PurposeProfile, run_purpose
from embody_data.storage import PurposeReader
from tests.fixtures.genrobot_fixture import write_genrobot_fixture


def _tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_same_normalized_run_produces_isolated_archival_and_exploration_runs(tmp_path):
    raw = write_genrobot_fixture(tmp_path / "fixture.mcap")
    processed = tmp_path / "processed" / "fixture" / "normalized-1"
    process_genrobot_mcap(raw, processed, {})
    processed_before = _tree_hash(processed)

    archival_dir = tmp_path / "purpose" / "fixture" / "archival" / "run-1"
    exploration_dir = tmp_path / "purpose" / "fixture" / "exploration" / "run-1"
    archival = PurposeProfile("local_archival", PurposeKind.ARCHIVAL, "0.1.0")
    exploration = PurposeProfile(
        "local_exploration", PurposeKind.EXPLORATION, "0.1.0", {"preview_stride": 2}
    )

    run_purpose(processed, archival_dir, archival)
    run_purpose(processed, exploration_dir, exploration)

    assert _tree_hash(processed) == processed_before
    assert archival_dir != exploration_dir
    for root in (archival_dir, exploration_dir):
        assert (root / "purpose_manifest.json").is_file()
        assert (root / "purpose_qc.json").is_file()
        assert (root / "purpose_status.json").is_file()
        assert (root / "provenance.json").is_file()

    archival_reader = PurposeReader(archival_dir)
    exploration_reader = PurposeReader(exploration_dir)
    assert archival_reader.manifest["profile"]["purpose"] == "archival"
    assert exploration_reader.manifest["profile"]["purpose"] == "exploration"
    assert archival_reader.provenance()["raw_decode_performed"] is False
    assert archival_reader.provenance()["normalized_data_modified"] is False
    assert archival_reader.status()["state"] == "succeeded"
    assert all(path.is_file() for path in archival_reader.artifact_paths())
    assert archival_reader.manifest["validity_masks"][0]["kind"] == ("selected_streams_validity")

    exploration_qc = exploration_reader.qc()
    assert exploration_qc["source_findings_preserved"] is True
    assert exploration_qc["source_qc_verdict"] == "warn"
    assert exploration_qc["verdict"] == "warn"
    assert {item["kind"] for item in exploration_reader.manifest["artifacts"]} == {
        "preview_index",
        "summary_statistics",
    }
    preview = json.loads(
        (exploration_dir / "artifacts" / "preview_index.json").read_text(encoding="utf-8")
    )
    assert preview["stride"] == 2


def test_purpose_run_refuses_to_overwrite(tmp_path):
    output = tmp_path / "purpose"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")
    profile = PurposeProfile("local_archival", PurposeKind.ARCHIVAL, "0.1.0")

    try:
        run_purpose(tmp_path / "processed", output, profile)
    except Exception as error:
        assert getattr(error, "code", None) == "output_not_empty"
    else:
        raise AssertionError("Expected overwrite protection")


def test_missing_processed_run_emits_structured_failure_status(tmp_path):
    output = tmp_path / "purpose"
    profile = PurposeProfile("local_archival", PurposeKind.ARCHIVAL, "0.1.0")

    try:
        run_purpose(tmp_path / "missing", output, profile)
    except FileNotFoundError:
        status = json.loads((output / "purpose_status.json").read_text(encoding="utf-8"))
        assert status["state"] == "failed"
        assert status["error"]["code"] == "unexpected_error"
    else:
        raise AssertionError("Expected missing processed run to fail")
