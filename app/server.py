#!/usr/bin/env python3
"""Small local API for the Motiva operations prototype."""

from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
PORT = 8787
DB_PATH = Path(os.environ.get("MOTIVA_DB_PATH", Path(__file__).with_name("motiva.sqlite3")))
SEED_MISSIONS = (
    (2048, "انبار مواد اولیه", "خط تولید A", "R-07", "done", "10:24"),
    (2047, "خط تولید B", "بسته‌بندی", "R-12", "running", "10:29"),
    (2046, "بارگیری", "انبار محصول", "R-03", "waiting", "10:31"),
)


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize_db() -> None:
    with connection() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                robot TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('done', 'running', 'waiting')),
                started_at TEXT NOT NULL
            )
            """
        )
        if not db.execute("SELECT 1 FROM missions LIMIT 1").fetchone():
            db.executemany("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)", SEED_MISSIONS)


def mission_payload(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": f"M-{row['id']}",
        "origin": row["origin"],
        "destination": row["destination"],
        "robot": row["robot"],
        "status": row["status"],
        "started_at": row["started_at"],
    }


def response_payload() -> dict[str, Any]:
    with connection() as db:
        rows = db.execute("SELECT * FROM missions ORDER BY id DESC LIMIT 10").fetchall()
    return {
        "fleet": {"online": 18, "total": 20, "utilization": 93, "average_battery": 78},
        "missions": {"active": 42, "cycle_minutes": 4.8, "items": [mission_payload(row) for row in rows]},
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

        with connection() as db:
            next_id = db.execute("SELECT COALESCE(MAX(id), 2048) + 1 FROM missions").fetchone()[0]
            db.execute(
                "INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)",
                (next_id, payload["origin"].strip(), payload["destination"].strip(), "تخصیص خودکار", "waiting", "اکنون"),
            )
            row = db.execute("SELECT * FROM missions WHERE id = ?", (next_id,)).fetchone()
        self._send(201, {"mission": mission_payload(row)})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    initialize_db()
    print(f"Motiva API listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
