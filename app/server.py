#!/usr/bin/env python3
"""Small local API for the Motiva operations prototype."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from navigation import shortest_path
from integration import decode_event, valid_signature

HOST = "127.0.0.1"
PORT = 8787
DB_PATH = Path(os.environ.get("MOTIVA_DB_PATH", Path(__file__).with_name("motiva.sqlite3")))
UNASSIGNED_ROBOT = "تخصیص خودکار"
MISSION_COLUMNS = "id, origin, destination, robot, status, started_at"
ROBOT_STATUSES = {"moving", "waiting", "charging", "offline"}
SEED_MISSIONS = (
    (2048, "انبار مواد اولیه", "خط تولید A", "R-07", "done", "10:24"),
    (2047, "خط تولید B", "بسته‌بندی", "R-12", "running", "10:29"),
    (2046, "بارگیری", "انبار محصول", "R-03", "waiting", "10:31"),
)
SEED_ROBOTS = (
    ("R-01", "moving", 86, 19, 42),
    ("R-07", "moving", 72, 47, 37),
    ("R-04", "waiting", 64, 57, 59),
    ("R-12", "charging", 91, 28, 76),
)
MISSION_PATH = re.compile(r"^/api/missions/(\d+)/(assign|cancel)$")


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize_db() -> None:
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        schema = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'missions'").fetchone()
        migrate = schema is not None and "'cancelled'" not in schema["sql"]
        if migrate:
            db.execute("ALTER TABLE missions RENAME TO missions_legacy")
        db.execute("""CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY, origin TEXT NOT NULL, destination TEXT NOT NULL,
            robot TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('done', 'running', 'waiting', 'cancelled')),
            started_at TEXT NOT NULL)""")
        if migrate:
            db.execute(f"INSERT INTO missions ({MISSION_COLUMNS}) SELECT {MISSION_COLUMNS} FROM missions_legacy")
            db.execute("DROP TABLE missions_legacy")
        db.execute("""CREATE TABLE IF NOT EXISTS integration_events (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)
        """)
        db.execute("""CREATE TABLE IF NOT EXISTS telemetry_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, robot_id TEXT NOT NULL, status TEXT NOT NULL,
            battery INTEGER NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(robot_id) REFERENCES robots(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS mission_details (
            mission_id INTEGER PRIMARY KEY, cargo TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'normal',
            deadline TEXT, source TEXT NOT NULL DEFAULT 'manual', progress INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(mission_id) REFERENCES missions(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS robots (
            id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('moving', 'waiting', 'charging', 'offline')),
            battery INTEGER NOT NULL CHECK(battery BETWEEN 0 AND 100), x INTEGER NOT NULL,
            y INTEGER NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS map_nodes (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('zone', 'station')),
            name TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS map_edges (
            source TEXT NOT NULL, target TEXT NOT NULL,
            PRIMARY KEY(source, target),
            FOREIGN KEY(source) REFERENCES map_nodes(id), FOREIGN KEY(target) REFERENCES map_nodes(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS map_obstacles (
            node_id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(node_id) REFERENCES map_nodes(id))""")
        if not db.execute("SELECT 1 FROM missions LIMIT 1").fetchone():
            db.executemany("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)", SEED_MISSIONS)
        db.execute("INSERT OR IGNORE INTO mission_details(mission_id) SELECT id FROM missions")
        if not db.execute("SELECT 1 FROM robots LIMIT 1").fetchone():
            db.executemany("INSERT INTO robots(id, status, battery, x, y) VALUES (?, ?, ?, ?, ?)", SEED_ROBOTS)


def mission_payload(row: sqlite3.Row) -> dict[str, Any]:
    with connection() as db:
        detail = db.execute("SELECT cargo, priority, deadline, source, progress FROM mission_details WHERE mission_id = ?", (row["id"],)).fetchone()
    return {
        "id": f"M-{row['id']}",
        "origin": row["origin"],
        "destination": row["destination"],
        "robot": row["robot"],
        "status": row["status"],
        "started_at": row["started_at"],
        "assigned": row["robot"] != UNASSIGNED_ROBOT,
        "cargo": detail["cargo"] if detail else "",
        "priority": detail["priority"] if detail else "normal",
        "deadline": detail["deadline"] if detail else None,
        "source": detail["source"] if detail else "manual",
        "progress": detail["progress"] if detail else 0,
    }


def robot_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "status": row["status"], "battery": row["battery"], "position": {"x": row["x"], "y": row["y"]}, "updated_at": row["updated_at"]}


def response_payload() -> dict[str, Any]:
    with connection() as db:
        missions = db.execute("SELECT * FROM missions ORDER BY id DESC LIMIT 10").fetchall()
        robots = db.execute("SELECT * FROM robots ORDER BY id").fetchall()
        active = db.execute("SELECT COUNT(*) FROM missions WHERE status IN ('running', 'waiting')").fetchone()[0]
    online = sum(row["status"] != "offline" for row in robots)
    average_battery = round(sum(row["battery"] for row in robots) / len(robots)) if robots else 0
    return {
        "fleet": {"online": online, "total": len(robots), "utilization": None, "average_battery": average_battery},
        "robots": [robot_payload(row) for row in robots],
        "missions": {"active": active, "cycle_minutes": None, "items": [mission_payload(row) for row in missions]},
        "system": {"core": None, "wms": None, "status": "prototype"},
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

    def _read_json(self) -> Any:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                return None
            self.raw_body = self.rfile.read(size)
            return json.loads(self.raw_body)
        except (ValueError, UnicodeDecodeError):
            return None

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
        elif self.path == "/api/robots":
            with connection() as db:
                rows = db.execute("SELECT * FROM robots ORDER BY id").fetchall()
            self._send(200, {"robots": [robot_payload(row) for row in rows]})
        elif self.path == "/api/map":
            self.get_map()
        elif self.path == "/api/alerts":
            self.get_alerts()
        elif self.path == "/api/reports":
            self.get_report()
        else:
            self._send(404, {"error": "route_not_found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        payload = self._read_json()
        if payload is None:
            self._send(400, {"error": "invalid_json"})
            return
        if path == "/api/integrations/events":
            self.receive_integration_event(payload)
            return
        if path == "/api/map/nodes":
            self.add_map_node(payload)
            return
        if path == "/api/map/edges":
            self.add_map_edge(payload)
            return
        if path == "/api/map/obstacles":
            self.set_obstacle(payload)
            return
        if path == "/api/map/route":
            self.calculate_route(payload)
            return
        if path == "/api/missions":
            self.create_mission(payload)
            return
        if path == "/api/telemetry":
            self.update_telemetry(payload)
            return
        match = MISSION_PATH.match(path)
        if match:
            command = match.group(2)
            self.assign_mission(int(match.group(1)), payload) if command == "assign" else self.cancel_mission(int(match.group(1)))
        else:
            self._send(404, {"error": "route_not_found"})

    def receive_integration_event(self, payload: Any) -> None:
        secret = os.environ.get("MOTIVA_WEBHOOK_SECRET")
        if not secret:
            self._send(503, {"error": "webhook_not_configured"})
            return
        if not valid_signature(self.raw_body, self.headers.get("X-Motiva-Signature"), secret) or decode_event(self.raw_body) is None:
            self._send(401, {"error": "invalid_webhook"})
            return
        event = decode_event(self.raw_body)
        with connection() as db:
            inserted = db.execute("INSERT OR IGNORE INTO integration_events(event_id, event_type) VALUES (?, ?)", (event["id"], event["type"])).rowcount
            if inserted and event["type"] == "transport_request.created":
                data = event["data"]
                if not isinstance(data.get("origin"), str) or not isinstance(data.get("destination"), str) or not data["origin"].strip() or not data["destination"].strip():
                    self._send(422, {"error": "transport_request_is_incomplete"})
                    return
                next_id = db.execute("SELECT COALESCE(MAX(id), 2048) + 1 FROM missions").fetchone()[0]
                db.execute("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)", (next_id, data["origin"].strip(), data["destination"].strip(), UNASSIGNED_ROBOT, "waiting", "اکنون"))
                db.execute("INSERT INTO mission_details(mission_id, source) VALUES (?, 'wms')", (next_id,))
        self._send(200, {"accepted": True, "duplicate": not bool(inserted)})

    def get_alerts(self) -> None:
        with connection() as db:
            robots = db.execute("SELECT id, status, battery FROM robots WHERE status = 'offline' OR battery <= 20 ORDER BY id").fetchall()
            missions = db.execute("SELECT id, origin, destination FROM missions WHERE status = 'waiting' ORDER BY id").fetchall()
        alerts = [{"type": "robot_offline" if row["status"] == "offline" else "low_battery", "severity": "critical" if row["status"] == "offline" else "warning", "robot": row["id"], "battery": row["battery"]} for row in robots]
        alerts.extend({"type": "mission_waiting", "severity": "info", "mission": f"M-{row['id']}", "origin": row["origin"], "destination": row["destination"]} for row in missions)
        self._send(200, {"alerts": alerts})

    def get_report(self) -> None:
        with connection() as db:
            totals = db.execute("SELECT COUNT(*) AS total, SUM(status = 'done') AS completed, SUM(status IN ('running', 'waiting')) AS active FROM missions").fetchone()
            robots = db.execute("SELECT COUNT(*) AS total, SUM(status != 'offline') AS online FROM robots").fetchone()
            telemetry = db.execute("SELECT COUNT(*) FROM telemetry_history").fetchone()[0]
        total_robots = robots["total"] or 0
        self._send(200, {"period": "all", "missions": {"total": totals["total"], "completed": totals["completed"] or 0, "active": totals["active"] or 0}, "fleet": {"total": total_robots, "online": robots["online"] or 0, "utilization": round((robots["online"] or 0) / total_robots * 100) if total_robots else 0}, "telemetry_samples": telemetry})

    def get_map(self) -> None:
        with connection() as db:
            nodes = [dict(row) for row in db.execute("SELECT * FROM map_nodes ORDER BY id")]
            edges = [dict(row) for row in db.execute("SELECT source, target FROM map_edges ORDER BY source, target")]
            obstacles = [row[0] for row in db.execute("SELECT node_id FROM map_obstacles WHERE active = 1")]
        self._send(200, {"nodes": nodes, "edges": edges, "obstacles": obstacles})

    def add_map_node(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"].strip() or payload.get("kind") not in {"zone", "station"} or not isinstance(payload.get("name"), str) or not payload["name"].strip():
            self._send(422, {"error": "invalid_map_node"})
            return
        with connection() as db:
            db.execute("INSERT OR REPLACE INTO map_nodes(id, kind, name) VALUES (?, ?, ?)", (payload["id"].strip(), payload["kind"], payload["name"].strip()))
        self._send(201, {"node": {"id": payload["id"].strip(), "kind": payload["kind"], "name": payload["name"].strip()}})

    def add_map_edge(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not all(isinstance(payload.get(key), str) and payload[key].strip() for key in ("source", "target")) or payload["source"] == payload["target"]:
            self._send(422, {"error": "invalid_map_edge"})
            return
        with connection() as db:
            known = db.execute("SELECT COUNT(*) FROM map_nodes WHERE id IN (?, ?)", (payload["source"], payload["target"])).fetchone()[0]
            if known != 2:
                self._send(422, {"error": "map_node_not_found"})
                return
            db.execute("INSERT OR IGNORE INTO map_edges(source, target) VALUES (?, ?)", (payload["source"], payload["target"]))
        self._send(201, {"edge": {"source": payload["source"], "target": payload["target"]}})

    def set_obstacle(self, payload: Any) -> None:
        node_id = payload.get("node_id") if isinstance(payload, dict) else None
        active = payload.get("active", True) if isinstance(payload, dict) else True
        if not isinstance(node_id, str) or not node_id.strip() or not isinstance(active, bool):
            self._send(422, {"error": "invalid_obstacle"})
            return
        with connection() as db:
            if db.execute("SELECT 1 FROM map_nodes WHERE id = ?", (node_id,)).fetchone() is None:
                self._send(404, {"error": "map_node_not_found"})
                return
            db.execute("INSERT OR REPLACE INTO map_obstacles(node_id, active) VALUES (?, ?)", (node_id, int(active)))
        self._send(200, {"node_id": node_id, "active": active})

    def calculate_route(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not all(isinstance(payload.get(key), str) and payload[key].strip() for key in ("start", "goal")):
            self._send(422, {"error": "route_endpoints_are_required"})
            return
        with connection() as db:
            edges = db.execute("SELECT source, target FROM map_edges").fetchall()
            blocked = [row[0] for row in db.execute("SELECT node_id FROM map_obstacles WHERE active = 1")]
        path = shortest_path(((row["source"], row["target"]) for row in edges), payload["start"], payload["goal"], blocked)
        if not path:
            self._send(409, {"error": "route_not_found"})
            return
        self._send(200, {"path": path})

    def create_mission(self, payload: Any) -> None:
        required = ("origin", "destination")
        if not isinstance(payload, dict) or any(not isinstance(payload.get(field), str) or not payload[field].strip() for field in required):
            self._send(422, {"error": "origin_and_destination_are_required"})
            return
        priority = payload.get("priority", "normal")
        cargo = payload.get("cargo", "")
        deadline = payload.get("deadline")
        source = payload.get("source", "manual")
        if priority not in {"urgent", "high", "normal", "low"} or not isinstance(cargo, str) or not isinstance(source, str) or source not in {"manual", "wms"} or (deadline is not None and not isinstance(deadline, str)):
            self._send(422, {"error": "invalid_mission_details"})
            return
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            next_id = db.execute("SELECT COALESCE(MAX(id), 2048) + 1 FROM missions").fetchone()[0]
            db.execute("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)", (next_id, payload["origin"].strip(), payload["destination"].strip(), UNASSIGNED_ROBOT, "waiting", "اکنون"))
            db.execute("INSERT INTO mission_details(mission_id, cargo, priority, deadline, source) VALUES (?, ?, ?, ?, ?)", (next_id, cargo.strip(), priority, deadline, source))
            row = db.execute("SELECT * FROM missions WHERE id = ?", (next_id,)).fetchone()
        self._send(201, {"mission": mission_payload(row)})

    def assign_mission(self, mission_id: int, payload: Any) -> None:
        robot_id = payload.get("robot") if isinstance(payload, dict) else None
        if not isinstance(robot_id, str) or not robot_id.strip():
            self._send(422, {"error": "robot_id_is_required"})
            return
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            mission = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
            robot = db.execute("SELECT * FROM robots WHERE id = ?", (robot_id.strip(),)).fetchone()
            if mission is None:
                self._send(404, {"error": "mission_not_found"})
                return
            if robot is None:
                self._send(422, {"error": "robot_not_found"})
                return
            if robot["status"] == "offline":
                self._send(409, {"error": "robot_offline"})
                return
            if mission["status"] not in {"waiting", "cancelled"}:
                self._send(409, {"error": "mission_not_assignable"})
                return
            db.execute("UPDATE missions SET robot = ?, status = 'running', started_at = 'اکنون' WHERE id = ?", (robot["id"], mission_id))
            row = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        self._send(200, {"mission": mission_payload(row)})

    def cancel_mission(self, mission_id: int) -> None:
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            mission = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
            if mission is None:
                self._send(404, {"error": "mission_not_found"})
                return
            if mission["status"] != "waiting":
                self._send(409, {"error": "only_waiting_missions_can_be_cancelled"})
                return
            db.execute("UPDATE missions SET status = 'cancelled' WHERE id = ?", (mission_id,))
            row = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        self._send(200, {"mission": mission_payload(row)})

    def update_telemetry(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
            self._send(422, {"error": "robot_id_is_required"})
            return
        status = payload.get("status")
        battery = payload.get("battery")
        position = payload.get("position")
        if (not isinstance(status, str) or status not in ROBOT_STATUSES
                or type(battery) is not int or not 0 <= battery <= 100
                or not isinstance(position, dict)
                or not all(type(position.get(axis)) is int and 0 <= position[axis] <= 100 for axis in ("x", "y"))):
            self._send(422, {"error": "invalid_telemetry"})
            return
        with connection() as db:
            cursor = db.execute("UPDATE robots SET status = ?, battery = ?, x = ?, y = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, battery, position["x"], position["y"], payload["id"]))
            if cursor.rowcount:
                db.execute("INSERT INTO telemetry_history(robot_id, status, battery, x, y) VALUES (?, ?, ?, ?, ?)", (payload["id"], status, battery, position["x"], position["y"]))
            row = db.execute("SELECT * FROM robots WHERE id = ?", (payload["id"],)).fetchone()
        if cursor.rowcount == 0:
            self._send(404, {"error": "robot_not_found"})
            return
        self._send(200, {"robot": robot_payload(row)})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    initialize_db()
    print(f"Motiva API listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
