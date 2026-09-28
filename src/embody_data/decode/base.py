from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from embody_data.errors import EmbodyDataError


@dataclass(frozen=True, slots=True)
class DecodedSample:
    stream_id: str
    source_timestamp: int | float
    sequence_id: int | str | None
    payload: Any
    source_fields: dict[str, str]


class Decoder(Protocol):
    name: str
    version: str

    def iter_samples(
        self,
        *,
        streams: set[str] | None = None,
        start: float | None = None,
        end: float | None = None,
    ) -> Iterator[DecodedSample]: ...


@dataclass(frozen=True, slots=True)
class AdapterKey:
    container: str
    encoding: str
    source_profile: str


@dataclass(frozen=True, slots=True)
class DecodeRequest:
    source: Path
    streams_dir: Path
    assets_dir: Path
    streams: frozenset[str] | None = None
    start: int | None = None
    end: int | None = None


class DecodeAdapter(Protocol):
    key: AdapterKey
    name: str
    version: str

    def decode(self, request: DecodeRequest) -> Any: ...


_ADAPTERS: dict[AdapterKey, DecodeAdapter] = {}


def register_adapter(adapter: DecodeAdapter, *, replace: bool = False) -> None:
    if adapter.key in _ADAPTERS and not replace:
        raise ValueError(f"Decoder adapter is already registered: {adapter.key}")
    _ADAPTERS[adapter.key] = adapter


def resolve_adapter(key: AdapterKey) -> DecodeAdapter:
    try:
        return _ADAPTERS[key]
    except KeyError as exc:
        raise EmbodyDataError(
            "decoder_not_found",
            "No decoder adapter is registered for the source contract.",
            {
                "container": key.container,
                "encoding": key.encoding,
                "source_profile": key.source_profile,
            },
        ) from exc


def registered_adapter_keys() -> tuple[AdapterKey, ...]:
    return tuple(
        sorted(
            _ADAPTERS,
            key=lambda item: (item.container, item.encoding, item.source_profile),
        )
    )


def dispatch_decode(key: AdapterKey, request: DecodeRequest) -> Any:
    return resolve_adapter(key).decode(request)
