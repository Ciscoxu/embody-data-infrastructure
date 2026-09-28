from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from embody_data import __version__
from embody_data.acquisition import acquire_genrobot, list_genrobot_files
from embody_data.config import load_config
from embody_data.errors import EmbodyDataError
from embody_data.ingestion import inspect_raw, resolve_inspector
from embody_data.logging import configure_logging
from embody_data.processing import process_recording
from embody_data.purpose import PurposeProfile, run_purpose


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="embody-data")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="Inventory raw data")
    inspect_parser.add_argument("raw_path", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)
    inspect_parser.add_argument("--config", type=Path)

    list_parser = commands.add_parser("source-list", help="List remote GenRobot MCAP objects")
    list_parser.add_argument("--revision", default="main")
    list_parser.add_argument("--path-prefix")
    list_parser.add_argument("--limit", type=int, default=20)

    acquire_parser = commands.add_parser("acquire", help="Acquire bounded GenRobot MCAP samples")
    acquire_parser.add_argument("--output", type=Path, required=True)
    acquire_parser.add_argument("--revision", default="main")
    acquire_parser.add_argument("--path", action="append", dest="paths")
    acquire_parser.add_argument("--max-files", type=int, default=3)
    acquire_parser.add_argument("--max-bytes", type=int, default=2 * 1024**3)
    acquire_parser.add_argument("--dry-run", action="store_true")
    acquire_parser.add_argument("--no-resume", action="store_true")

    process_parser = commands.add_parser("process", help="Run the Phase 1 GenRobot MCAP MVP")
    process_parser.add_argument("path", type=Path)
    process_parser.add_argument("--output", type=Path)
    process_parser.add_argument("--config", type=Path)

    purpose_parser = commands.add_parser(
        "purpose", help="Create a local purpose projection from processed data"
    )
    purpose_parser.add_argument("path", type=Path)
    purpose_parser.add_argument("--output", type=Path, required=True)
    purpose_parser.add_argument("--config", type=Path, required=True)

    for name in ("validate", "describe"):
        command = commands.add_parser(name, help=f"Read processed {name} output")
        command.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    try:
        if args.command == "inspect":
            config = load_config(args.config)
            if args.raw_path.is_file():
                try:
                    inspector = resolve_inspector(args.raw_path)
                except EmbodyDataError as exc:
                    if exc.code != "inspector_not_found":
                        raise
                    inspector = None
                if inspector is not None:
                    manifest = inspector.inspect(args.raw_path, args.output)
                    count = len(manifest["topics"])
                    recording_id = args.raw_path.stem
                else:
                    raw_manifest = inspect_raw(args.raw_path, args.output, config)
                    count = len(raw_manifest.files)
                    recording_id = raw_manifest.recording_id
            else:
                raw_manifest = inspect_raw(args.raw_path, args.output, config)
                count = len(raw_manifest.files)
                recording_id = raw_manifest.recording_id
            _print_json(
                {
                    "status": "succeeded",
                    "recording_id": recording_id,
                    "item_count": count,
                    "file_count": count,
                    "output": str(args.output),
                }
            )
            return 0
        if args.command == "source-list":
            revision, files = list_genrobot_files(
                revision=args.revision,
                path_prefix=args.path_prefix,
                max_results=max(1, args.limit),
            )
            _print_json(
                {
                    "status": "succeeded",
                    "resolved_revision": revision,
                    "total_mcap_files": len(files),
                    "files": [asdict(file) for file in files[: max(0, args.limit)]],
                }
            )
            return 0
        if args.command == "acquire":
            manifest = acquire_genrobot(
                args.output,
                revision=args.revision,
                paths=args.paths,
                max_files=args.max_files,
                max_bytes=args.max_bytes,
                dry_run=args.dry_run,
                resume=not args.no_resume,
            )
            _print_json(
                {
                    "status": manifest["state"],
                    "output": str(args.output),
                    "files": manifest["files"],
                }
            )
            return 0 if manifest["state"] in {"succeeded", "dry_run"} else 3
        if args.command == "process":
            if args.output is None:
                raise EmbodyDataError("output_required", "The process command requires --output.")
            manifest = process_recording(args.path, args.output, load_config(args.config))
            _print_json(
                {
                    "status": "succeeded",
                    "output": str(args.output),
                    "stream_count": len(manifest["streams"]),
                }
            )
            return 0
        if args.command == "purpose":
            profile = PurposeProfile.from_dict(load_config(args.config))
            run = run_purpose(args.path, args.output, profile)
            _print_json(
                {
                    "status": "succeeded",
                    "output": str(args.output),
                    "purpose": run.profile.purpose,
                    "artifact_count": len(run.artifacts),
                }
            )
            return 0
        if args.command in {"validate", "describe"}:
            target = args.path / (
                "qc/qc_report.json"
                if args.command == "validate"
                else "metadata/processed_manifest.json"
            )
            if not target.is_file():
                raise EmbodyDataError(
                    "processed_output_missing", f"Missing processed artifact: {target}"
                )
            _print_json(json.loads(target.read_text(encoding="utf-8")))
            return 0
        raise EmbodyDataError("unknown_command", f"Unknown command: {args.command}")
    except EmbodyDataError as exc:
        _print_json({"status": "failed", "error": exc.to_dict()}, stream=sys.stderr)
        return 2
    except Exception as exc:  # last-resort CLI boundary; detailed traceback is verbose-only later
        error = EmbodyDataError(
            "unexpected_error", "Unexpected command failure", {"reason": str(exc)}
        )
        _print_json({"status": "failed", "error": error.to_dict()}, stream=sys.stderr)
        return 1


def _print_json(value: object, *, stream: TextIO | None = None) -> None:
    print(json.dumps(value, sort_keys=True), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
