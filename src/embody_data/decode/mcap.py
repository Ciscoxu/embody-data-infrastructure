from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from embody_data.errors import EmbodyDataError


@dataclass(frozen=True, slots=True)
class McapDecodedMessage:
    topic: str
    channel_id: int
    schema_id: int | None
    schema_name: str
    schema_encoding: str
    message_encoding: str
    log_time_ns: int
    publish_time_ns: int
    decoded: Any


def iter_decoded(
    path: Path,
    *,
    topics: set[str] | None = None,
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> Iterator[McapDecodedMessage]:
    if start_time_ns is not None and end_time_ns is not None and start_time_ns >= end_time_ns:
        raise EmbodyDataError(
            "invalid_time_range",
            "Decode start_time_ns must be less than end_time_ns.",
            {"start_time_ns": start_time_ns, "end_time_ns": end_time_ns},
        )
    try:
        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
    except ImportError as exc:  # pragma: no cover - packaging error
        raise EmbodyDataError("dependency_missing", "MCAP dependencies are not installed.") from exc
    try:
        with path.open("rb") as handle:
            reader = make_reader(handle, decoder_factories=[DecoderFactory()])
            for schema, channel, message, decoded in reader.iter_decoded_messages(
                topics=topics,
                start_time=start_time_ns,
                end_time=end_time_ns,
                log_time_order=False,
            ):
                yield McapDecodedMessage(
                    topic=channel.topic,
                    channel_id=channel.id,
                    schema_id=schema.id if schema else None,
                    schema_name=schema.name if schema else "unknown",
                    schema_encoding=schema.encoding if schema else "unknown",
                    message_encoding=channel.message_encoding,
                    log_time_ns=message.log_time,
                    publish_time_ns=message.publish_time,
                    decoded=decoded,
                )
    except OSError as exc:
        raise EmbodyDataError(
            "mcap_read_error", f"Unable to read MCAP: {path}", {"reason": str(exc)}
        ) from exc


def header_fields(message: Any) -> tuple[int | None, int | str | None, str]:
    header = getattr(message, "header", None)
    timestamp = getattr(header, "timestamp", None)
    sequence = getattr(header, "sequence_num", None)
    frame_id = str(getattr(message, "frame_id", "") or getattr(header, "frame_id", "") or "unknown")
    return (_timestamp_ns(timestamp), sequence, frame_id)


def _timestamp_ns(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    seconds = getattr(value, "seconds", None)
    nanos = getattr(value, "nanos", None)
    if seconds is not None:
        return int(seconds) * 1_000_000_000 + int(nanos or 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
