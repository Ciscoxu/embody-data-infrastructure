from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from embody_data.errors import EmbodyDataError


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise EmbodyDataError("config_not_found", f"Config file does not exist: {path}")

    suffix = path.suffix.lower()
    try:
        with path.open("rb") as handle:
            if suffix == ".toml":
                return tomllib.load(handle)
            raw = handle.read()
        if suffix == ".json":
            value = json.loads(raw)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-untyped]
            except ImportError as exc:
                raise EmbodyDataError(
                    "yaml_support_missing",
                    "Install the optional 'yaml' dependency to read YAML configs.",
                ) from exc
            value = yaml.safe_load(raw)
        else:
            raise EmbodyDataError("unsupported_config", f"Unsupported config format: {suffix}")
    except (OSError, ValueError) as exc:
        raise EmbodyDataError(
            "invalid_config", f"Unable to load config: {path}", {"reason": str(exc)}
        ) from exc

    if not isinstance(value, dict):
        raise EmbodyDataError("invalid_config", "Top-level config value must be an object.")
    return value
