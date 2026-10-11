#!/usr/bin/env python3
"""Small local API for the Motiva operations prototype."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
PORT = 8787

MISSIONS: list[dict[str, Any]] = [
    {
        "id": "M-2048",
        "origin": "انبار مواد اولیه",
        "destination": "خط تولید A",
        "robot": "R-07",
        "status": "done",
        "started_at": "10:24",
    },
    {
        "id": "M-2047",
        "origin": "خط تولید B",
        "destination": "بسته‌بندی",
        "robot": "R-12",
        "status": "running",
        "started_at": "10:29",
    },
    {
        "id": "M-2046",
        "origin": "بارگیری",
        "destination": "انبار محصول",
        "robot": "R-03",
        "status": "waiting",
        "started_at": "10:31",
    },
]


def response_payload() -> dict[str, Any]:
    return {
        "fleet": {"online": 18, "total": 20, "utilization": 93, "average_battery": 78},
        "missions": {"active": 42, "cycle_minutes": 4.8, "items": MISSIONS},
        "system": {"core": 96, "wms": 100, "status": "healthy"},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/":
            body = (Path(__file__).parent / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/health":
            self._send(200, {"status": "healthy"})
        elif self.path == "/api/overview":
            self._send(200, response_payload())
        else:
            self._send(404, {"error": "route_not_found"})

    def do_POST(self) -> None:
        if self.path != "/api/missions":
            self._send(404, {"error": "route_not_found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size))
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid_json"})
            return

        required = ("origin", "destination")
        if not isinstance(payload, dict) or any(not isinstance(payload.get(field), str) or not payload[field].strip() for field in required):
            self._send(422, {"error": "origin_and_destination_are_required"})
            return

        mission = {
            "id": f"M-{2049 + len(MISSIONS)}",
            "origin": payload["origin"].strip(),
            "destination": payload["destination"].strip(),
            "robot": "تخصیص خودکار",
            "status": "waiting",
            "started_at": "اکنون",
        }
        MISSIONS.insert(0, mission)
        self._send(201, {"mission": mission})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    print(f"Motiva API listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
