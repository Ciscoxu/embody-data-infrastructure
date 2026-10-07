from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from demo.service_bridge import DemoPlatformBridge
from embody_data.errors import EmbodyDataError

COLLECTION_MODES = {"human_wearable", "teleop_device_only", "teleop_robot"}
INPUT_TYPES = {"mcap", "folder_bundle_v1"}
RECORDING_ROUTE = re.compile(r"^/api/recordings/([^/]+)$")
PROCESS_ROUTE = re.compile(r"^/api/recordings/([^/]+)/process$")
RUN_ROUTE = re.compile(r"^/api/runs/([^/]+)$")


@dataclass(frozen=True, slots=True)
class DemoStore:
    root: Path

    @property
    def bridge(self) -> DemoPlatformBridge:
        return DemoPlatformBridge(self.root)

    def create_recording(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = Path(str(payload.get("source_path", ""))).expanduser().resolve()
        mode = str(payload.get("collection_mode", ""))
        input_type = str(payload.get("input_type", ""))
        if mode not in COLLECTION_MODES:
            raise EmbodyDataError("collection_mode_invalid", "Select a valid collection mode.")
        if input_type not in INPUT_TYPES:
            raise EmbodyDataError("input_type_invalid", "Select a supported input type.")
        if not source.exists():
            raise EmbodyDataError("raw_not_found", f"Raw input does not exist: {source}")
        if input_type == "mcap" and not source.is_file():
            raise EmbodyDataError("mcap_not_file", "MCAP input must be a file.")
        if input_type == "folder_bundle_v1" and not source.is_dir():
            raise EmbodyDataError(
                "folder_bundle_not_directory", "Folder bundle must be a directory."
            )
        return self.bridge.register(
            {
                "source_path": str(source),
                "input_type": input_type,
                "collection_mode": mode,
                "operator_pseudonym": str(payload.get("operator_pseudonym") or "unknown"),
                "device_id": str(payload.get("device_id") or "unknown"),
                "rights": {
                    "consent": str(payload.get("consent") or "unknown"),
                    "license": str(payload.get("license") or "unknown"),
                    "privacy_redaction": str(payload.get("privacy_redaction") or "unknown"),
                    "permitted_use": str(payload.get("permitted_use") or "unknown"),
                },
            }
        )

    def list_recordings(self) -> list[dict[str, Any]]:
        return self.bridge.list_recordings()

    def get_recording(self, recording_id: str) -> dict[str, Any]:
        return self.bridge.get_recording(recording_id)

    def process(self, recording_id: str) -> dict[str, Any]:
        return self.bridge.process(recording_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.bridge.get_run(run_id)


def make_handler(store: DemoStore, index_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            try:
                if route == "/":
                    self._send(index_path.read_text(encoding="utf-8"), "text/html; charset=utf-8")
                    return
                if route == "/api/recordings":
                    self._json({"recordings": store.list_recordings()})
                    return
                if match := RECORDING_ROUTE.match(route):
                    self._json(store.get_recording(match.group(1)))
                    return
                if match := RUN_ROUTE.match(route):
                    self._json(store.get_run(match.group(1)))
                    return
                self._error(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found.")
            except EmbodyDataError as exc:
                self._error(HTTPStatus.BAD_REQUEST, exc.code, exc.message, exc.details)

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            try:
                if route == "/api/recordings":
                    self._json(store.create_recording(self._payload()), HTTPStatus.CREATED)
                    return
                if match := PROCESS_ROUTE.match(route):
                    self._json(store.process(match.group(1)), HTTPStatus.CREATED)
                    return
                self._error(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found.")
            except EmbodyDataError as exc:
                self._error(HTTPStatus.BAD_REQUEST, exc.code, exc.message, exc.details)
            except Exception as exc:
                self._error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "unexpected_error",
                    "Unexpected demo failure.",
                    {"reason": str(exc)},
                )

        def _payload(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                value = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError) as exc:
                raise EmbodyDataError("invalid_json", "Request body must be JSON.") from exc
            if not isinstance(value, dict):
                raise EmbodyDataError("invalid_json", "Request body must be a JSON object.")
            return value

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(json.dumps(value, indent=2), "application/json", status)

        def _error(
            self,
            status: HTTPStatus,
            code: str,
            message: str,
            details: dict[str, Any] | None = None,
        ) -> None:
            error = {"code": code, "message": message, "details": details or {}}
            self._json({"status": "failed", "error": error}, status)

        def _send(
            self,
            body: str,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local embodied-data demo platform.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", type=Path, default=Path(".local/demo-platform"))
    args = parser.parse_args()
    index_path = Path(__file__).with_name("platform.html")
    handler = make_handler(DemoStore(args.workspace), index_path)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Demo platform: http://{args.host}:{args.port}")
    print(f"Workspace: {args.workspace.resolve()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
