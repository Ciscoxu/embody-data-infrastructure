from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from embody_data import __version__
from embody_data.errors import EmbodyDataError
from embody_data.metadata.source_profiles import GENROBOT_REALOMIN


@dataclass(frozen=True, slots=True)
class RemoteFile:
    path: str
    size_bytes: int | None
    oid: str | None


def _hub() -> tuple[Any, Any, type[Exception], type[Any]]:
    try:
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.errors import HfHubHTTPError
        from huggingface_hub.hf_api import RepoFile
    except ImportError as exc:  # pragma: no cover - packaging error
        raise EmbodyDataError(
            "dependency_missing", "Install project dependencies to use Hugging Face acquisition."
        ) from exc
    return HfApi, hf_hub_download, HfHubHTTPError, RepoFile


def list_genrobot_files(
    *,
    revision: str = "main",
    path_prefix: str | None = None,
    max_results: int = 100,
    max_directories: int = 100,
) -> tuple[str, list[RemoteFile]]:
    """Find one bounded MCAP leaf without recursively walking the 95 TB repository."""
    HfApi, _, http_error, RepoFile = _hub()
    api = HfApi()
    try:
        info = api.dataset_info(GENROBOT_REALOMIN.dataset_repo_id, revision=revision)
        pending: list[str | None] = [path_prefix]
        visited = 0
        while pending and visited < max_directories:
            current = pending.pop()
            visited += 1
            entries = api.list_repo_tree(
                GENROBOT_REALOMIN.dataset_repo_id,
                path_in_repo=current,
                repo_type="dataset",
                revision=revision,
                recursive=False,
                expand=True,
            )
            files: list[RemoteFile] = []
            folders: list[str] = []
            for item in entries:
                if isinstance(item, RepoFile) and item.path.lower().endswith(".mcap"):
                    files.append(RemoteFile(item.path, item.size, _object_id(item)))
                    if len(files) >= max_results:
                        break
                elif not isinstance(item, RepoFile):
                    folders.append(item.path)
            if files:
                return str(info.sha), sorted(files, key=_size_key)
            pending.extend(sorted(folders, reverse=True))
        raise EmbodyDataError(
            "mcap_discovery_limit",
            "No MCAP leaf was found within the bounded directory scan.",
            {"path_prefix": path_prefix, "max_directories": max_directories},
        )
    except http_error as exc:
        raise _hub_error(exc) from exc


def resolve_genrobot_paths(
    paths: list[str], *, revision: str = "main"
) -> tuple[str, list[RemoteFile]]:
    HfApi, _, http_error, RepoFile = _hub()
    api = HfApi()
    try:
        info = api.dataset_info(GENROBOT_REALOMIN.dataset_repo_id, revision=revision)
        entries = api.get_paths_info(
            GENROBOT_REALOMIN.dataset_repo_id,
            paths,
            repo_type="dataset",
            revision=revision,
            expand=True,
        )
        files = [
            RemoteFile(item.path, item.size, _object_id(item))
            for item in entries
            if isinstance(item, RepoFile) and item.path.lower().endswith(".mcap")
        ]
        return str(info.sha), files
    except http_error as exc:
        raise _hub_error(exc) from exc


def select_files(
    files: Iterable[RemoteFile],
    *,
    paths: list[str] | None,
    max_files: int,
    max_bytes: int,
) -> list[RemoteFile]:
    if not 1 <= max_files <= 5:
        raise EmbodyDataError("unsafe_file_limit", "max_files must be between 1 and 5.")
    available = {item.path: item for item in files}
    if paths:
        missing = sorted(set(paths) - available.keys())
        if missing:
            raise EmbodyDataError(
                "remote_path_not_found", "Requested remote path is absent.", {"paths": missing}
            )
        selected = [available[path] for path in paths]
    else:
        groups: dict[str, list[RemoteFile]] = {}
        for item in available.values():
            groups.setdefault(str(PurePosixPath(item.path).parent), []).append(item)
        eligible = [sorted(group, key=_size_key) for group in groups.values() if group]
        if not eligible:
            raise EmbodyDataError("no_mcap_files", "No remote MCAP files were found.")
        selected = min(
            eligible,
            key=lambda group: sum(_known_size(item) for item in group[:max_files]),
        )[:max_files]
    if len(selected) > max_files:
        raise EmbodyDataError(
            "unsafe_file_limit",
            "Selection exceeds max_files.",
            {"selected": len(selected), "max_files": max_files},
        )
    unknown = [item.path for item in selected if item.size_bytes is None]
    if unknown:
        raise EmbodyDataError(
            "unknown_remote_size",
            "Refusing download because selected objects have unknown sizes.",
            {"paths": unknown},
        )
    total = sum(item.size_bytes or 0 for item in selected)
    if total > max_bytes:
        raise EmbodyDataError(
            "download_size_limit",
            "Selection exceeds max_download_bytes.",
            {"selected_bytes": total, "max_download_bytes": max_bytes},
        )
    return selected


def acquire_genrobot(
    output_dir: Path,
    *,
    revision: str = "main",
    paths: list[str] | None = None,
    max_files: int = 3,
    max_bytes: int = 2 * 1024**3,
    dry_run: bool = False,
    resume: bool = True,
) -> dict[str, Any]:
    """Acquire a bounded selection and always emit a credential-free status manifest."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "manifest_version": "0.1.0",
        "operation": "acquire",
        "state": "running",
        "started_at": _now(),
        "finished_at": None,
        "source": GENROBOT_REALOMIN.to_dict(),
        "requested_revision": revision,
        "resolved_revision": None,
        "selection_rule": {
            "explicit_paths": paths or [],
            "default": "smallest files from one task leaf directory",
            "max_files": max_files,
            "max_download_bytes": max_bytes,
        },
        "dry_run": dry_run,
        "resume": resume,
        "tool": {"name": "embody-data", "version": __version__},
        "download_tool": {
            "name": "huggingface-hub",
            "version": importlib.metadata.version("huggingface-hub"),
        },
        "gated_access_state": "requires_accepted_conditions",
        "files": [],
        "retries": [],
        "credential_source": "environment_or_huggingface_store",
    }
    status_path = output_dir / "acquisition_status.json"
    try:
        if paths:
            commit, remote = resolve_genrobot_paths(paths, revision=revision)
        else:
            commit, remote = list_genrobot_files(revision=revision, max_results=max_files)
        selected = select_files(remote, paths=paths, max_files=max_files, max_bytes=max_bytes)
        manifest["resolved_revision"] = commit
        manifest["estimated_bytes"] = sum(item.size_bytes or 0 for item in selected)
        for item in selected:
            manifest["files"].append(
                {
                    **asdict(item),
                    "local_relative_path": item.path,
                    "state": "planned" if dry_run else "pending",
                    "sha256": None,
                    "downloaded_at": None,
                    "attempts": 0,
                }
            )
        if dry_run:
            manifest["state"] = "dry_run"
        else:
            _, download, http_error, _ = _hub()
            for record in manifest["files"]:
                target = output_dir / record["local_relative_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_file() and target.stat().st_size == record["size_bytes"] and resume:
                    record.update(state="skipped", sha256=_sha256(target), attempts=0)
                    continue
                record["attempts"] = 1
                try:
                    downloaded = Path(
                        download(
                            GENROBOT_REALOMIN.dataset_repo_id,
                            filename=record["path"],
                            repo_type="dataset",
                            revision=commit,
                            local_dir=output_dir,
                            force_download=not resume,
                        )
                    )
                except http_error as exc:
                    error = _hub_error(exc)
                    record.update(state="failed", error=error.to_dict())
                    manifest["retries"].append(
                        {"path": record["path"], "attempt": 1, "outcome": error.code}
                    )
                    raise error from exc
                record.update(
                    state="succeeded",
                    local_relative_path=downloaded.relative_to(output_dir).as_posix(),
                    sha256=_sha256(downloaded),
                    downloaded_at=_now(),
                )
            manifest["state"] = "succeeded"
    except EmbodyDataError as exc:
        manifest["state"] = "blocked_auth" if exc.code == "blocked_auth" else "failed"
        manifest["error"] = exc.to_dict()
        for record in manifest["files"]:
            if record["state"] == "pending":
                record["state"] = "not_attempted"
    except Exception as exc:
        manifest["state"] = "failed"
        manifest["error"] = {
            "code": "unexpected_acquisition_error",
            "message": "Unexpected acquisition failure.",
            "details": {"reason": str(exc)},
        }
        for record in manifest["files"]:
            if record["state"] == "pending":
                record["state"] = "not_attempted"
    finally:
        manifest["finished_at"] = _now()
        status_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return manifest


def _hub_error(exc: Exception) -> EmbodyDataError:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status in {401, 403}:
        return EmbodyDataError(
            "blocked_auth",
            "Dataset access is gated. Accept the dataset conditions and authenticate "
            "with Hugging Face.",
            {"dataset_repo_id": GENROBOT_REALOMIN.dataset_repo_id, "http_status": status},
        )
    return EmbodyDataError(
        "huggingface_error", "Hugging Face request failed.", {"http_status": status}
    )


def _object_id(item: Any) -> str | None:
    lfs = getattr(item, "lfs", None)
    return str(getattr(lfs, "sha256", None) or "") or None


def _known_size(item: RemoteFile) -> int:
    return item.size_bytes if item.size_bytes is not None else 2**63 - 1


def _size_key(item: RemoteFile) -> tuple[int, str]:
    return (_known_size(item), item.path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
