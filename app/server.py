#!/usr/bin/env python3
"""Small local API for the Motiva operations prototype."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import charging
import dispatch
import traffic
import vda5050
from navigation import shortest_path
from integration import decode_event, valid_signature

HOST = os.environ.get("MOTIVA_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOTIVA_PORT", "8787"))
DB_PATH = Path(os.environ.get("MOTIVA_DB_PATH", Path(__file__).with_name("motiva.sqlite3")))
HEARTBEAT_TIMEOUT_SECONDS = float(os.environ.get("MOTIVA_HEARTBEAT_TIMEOUT_SECONDS", "30"))
MAP_EXTENT_METRES = float(os.environ.get("MOTIVA_MAP_EXTENT_METRES", "100"))
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
DISPATCH_PATH = re.compile(r"^/api/missions/(\d+)/dispatch$")
ROBOT_CHARGE_PATH = re.compile(r"^/api/robots/([^/]+)/charge$")


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        # Added later: heartbeat_at drives derived offline state, the rest carry
        # the VDA 5050 safety and order context the dashboard surfaces.
        existing = {row["name"] for row in db.execute("PRAGMA table_info(robots)")}
        for column, definition in (
            ("heartbeat_at", "REAL"),
            ("order_id", "TEXT"),
            ("e_stop", "TEXT NOT NULL DEFAULT 'NONE'"),
            ("field_violation", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in existing:
                db.execute(f"ALTER TABLE robots ADD COLUMN {column} {definition}")
        db.execute("""CREATE TABLE IF NOT EXISTS map_nodes (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('zone', 'station')),
            name TEXT NOT NULL)""")
        node_columns = {row["name"] for row in db.execute("PRAGMA table_info(map_nodes)")}
        for column in ("x", "y"):
            # Optional grid coordinates let dispatch use distance when a mission
            # origin names a placed node.
            if column not in node_columns:
                db.execute(f"ALTER TABLE map_nodes ADD COLUMN {column} INTEGER")
        db.execute("""CREATE TABLE IF NOT EXISTS map_edges (
            source TEXT NOT NULL, target TEXT NOT NULL,
            PRIMARY KEY(source, target),
            FOREIGN KEY(source) REFERENCES map_nodes(id), FOREIGN KEY(target) REFERENCES map_nodes(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS map_obstacles (
            node_id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(node_id) REFERENCES map_nodes(id))""")
        # One holder per node is enforced by the database, not just by code, so a
        # racing dispatcher cannot lease the same corridor twice.
        db.execute("""CREATE TABLE IF NOT EXISTS node_reservations (
            node_id TEXT PRIMARY KEY, robot_id TEXT NOT NULL, mission_id INTEGER,
            held_until REAL NOT NULL, acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(node_id) REFERENCES map_nodes(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS chargers (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, x INTEGER, y INTEGER)""")
        # One robot per charger, enforced by the primary key like corridors.
        db.execute("""CREATE TABLE IF NOT EXISTS charger_occupancies (
            charger_id TEXT PRIMARY KEY, robot_id TEXT NOT NULL,
            held_until REAL NOT NULL, since TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(charger_id) REFERENCES chargers(id))""")
        if not db.execute("SELECT 1 FROM missions LIMIT 1").fetchone():
            db.executemany("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)", SEED_MISSIONS)
        db.execute("INSERT OR IGNORE INTO mission_details(mission_id) SELECT id FROM missions")
        if not db.execute("SELECT 1 FROM robots LIMIT 1").fetchone():
            # Seeded robots get a current heartbeat so a fresh install renders as
            # online demo data that ages into offline exactly like real robots.
            db.executemany(
                "INSERT INTO robots(id, status, battery, x, y, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?)",
                ((*robot, time.time()) for robot in SEED_ROBOTS),
            )


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


def robot_payload(row: sqlite3.Row, now: float | None = None) -> dict[str, Any]:
    heartbeat = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
    stale = is_stale(heartbeat, now)
    status = "offline" if stale else row["status"]
    return {
        "id": row["id"],
        "status": status,
        "reported_status": row["status"],
        "stale": stale,
        "battery": row["battery"],
        "position": {"x": row["x"], "y": row["y"]},
        "updated_at": row["updated_at"],
        "heartbeat_at": heartbeat,
        "order_id": row["order_id"] if "order_id" in row.keys() else None,
        "e_stop": row["e_stop"] if "e_stop" in row.keys() else "NONE",
        "field_violation": bool(row["field_violation"]) if "field_violation" in row.keys() else False,
    }


def is_stale(heartbeat: float | None, now: float | None = None) -> bool:
    """A robot with no heartbeat or an old one is never treated as healthy."""
    if heartbeat is None:
        return True
    current = time.time() if now is None else now
    return current - heartbeat > HEARTBEAT_TIMEOUT_SECONDS


def dispatch_candidates(db: sqlite3.Connection, now: float | None = None) -> list[dict[str, Any]]:
    """Current fleet state shaped for the dispatch scorer."""
    workloads = {
        row["robot"]: row["count"]
        for row in db.execute(
            "SELECT robot, COUNT(*) AS count FROM missions WHERE status = 'running' GROUP BY robot"
        )
    }
    candidates = []
    for row in db.execute("SELECT * FROM robots ORDER BY id"):
        robot = robot_payload(row, now)
        candidates.append({
            "id": robot["id"],
            "status": robot["status"],
            "battery": robot["battery"],
            "position": robot["position"],
            "active_missions": workloads.get(robot["id"], 0),
        })
    return candidates


def origin_position(db: sqlite3.Connection, origin: str) -> dict[str, int] | None:
    """Resolve a mission origin to a placed map node, if it names one.

    Origins are free text in the prototype, so an unresolved origin simply
    drops the distance signal instead of guessing a location.
    """
    if not isinstance(origin, str) or not origin.strip():
        return None
    row = db.execute(
        "SELECT x, y FROM map_nodes WHERE id = ? AND x IS NOT NULL AND y IS NOT NULL",
        (origin.strip(),),
    ).fetchone()
    if row is None:
        return None
    return {"x": row["x"], "y": row["y"]}


def read_reservations(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {
            "node_id": row["node_id"],
            "robot_id": row["robot_id"],
            "mission_id": row["mission_id"],
            "held_until": row["held_until"],
        }
        for row in db.execute("SELECT * FROM node_reservations")
    ]


def claim_reservations(db: sqlite3.Connection, leases: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Insert leases inside the open transaction, refusing anything already held.

    Expired rows are cleared first so a dead lease cannot wedge a corridor. Every
    row must be inserted, otherwise the caller rolls back and the whole lease is
    refused rather than half of it.
    """
    db.execute("DELETE FROM node_reservations WHERE held_until <= ?", (now,))
    held = {row["node_id"]: row["robot_id"] for row in db.execute("SELECT node_id, robot_id FROM node_reservations")}
    for lease in leases:
        holder = held.get(lease["node_id"])
        if holder is not None and holder != lease["robot_id"]:
            return [{"node_id": lease["node_id"], "robot_id": holder}]
    db.executemany(
        "INSERT INTO node_reservations(node_id, robot_id, mission_id, held_until) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(node_id) DO UPDATE SET robot_id = excluded.robot_id, "
        "mission_id = excluded.mission_id, held_until = excluded.held_until",
        [(lease["node_id"], lease["robot_id"], lease["mission_id"], lease["held_until"]) for lease in leases],
    )
    return []


def release_reservations(db: sqlite3.Connection, *, robot_id: str | None = None, mission_id: int | None = None) -> int:
    """Drop leases for a finished/cancelled mission or a parked robot."""
    if robot_id is not None:
        return db.execute("DELETE FROM node_reservations WHERE robot_id = ?", (robot_id,)).rowcount
    if mission_id is not None:
        return db.execute("DELETE FROM node_reservations WHERE mission_id = ?", (mission_id,)).rowcount
    return 0


def route_between(db: sqlite3.Connection, start: str, goal: str, *, robot_id: str | None = None, now: float | None = None) -> dict[str, Any]:
    edges = db.execute("SELECT source, target FROM map_edges").fetchall()
    blocked = [row[0] for row in db.execute("SELECT node_id FROM map_obstacles WHERE active = 1")]
    return traffic.plan_route(
        ((row["source"], row["target"]) for row in edges),
        start,
        goal,
        blocked=blocked,
        reservations=read_reservations(db),
        robot_id=robot_id,
        now=time.time() if now is None else now,
    )


def lease_mission_route(
    db: sqlite3.Connection, mission_id: int, robot_id: str, origin: str, destination: str, now: float,
) -> dict[str, Any] | None:
    """Plan and lease the route for a newly assigned mission.

    Returns None when the mission names no located endpoints: there is no route
    to coordinate, so claiming traffic management would be a lie.
    """
    resolved = origin_position(db, origin)
    if resolved is None:
        return {"status": "unrouted", "reason": "origin_not_a_placed_node", "leased_nodes": []}
    if origin_position(db, destination) is None:
        return {"status": "unrouted", "reason": "destination_not_a_placed_node", "leased_nodes": []}

    result = route_between(db, origin.strip(), destination.strip(), robot_id=robot_id, now=now)
    if not result["path"]:
        return {"status": result["status"], "reason": "no_route_for_mission", "leased_nodes": [], "traffic_applied": result["traffic_applied"]}

    leases = traffic.lease_path(result["path"], robot_id=robot_id, mission_id=mission_id, now=now)
    conflicts = claim_reservations(db, leases, now)
    if conflicts:
        return {
            "status": "lease_conflict",
            "conflicts": conflicts,
            "leased_nodes": [],
            "traffic_applied": result["traffic_applied"],
        }
    return {
        "status": result["status"],
        "leased_nodes": [lease["node_id"] for lease in leases],
        "traffic_applied": result["traffic_applied"],
    }


def read_chargers(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return [read_chargers_row(row) for row in db.execute("SELECT * FROM chargers ORDER BY id")]


def read_occupancies(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {"charger_id": row["charger_id"], "robot_id": row["robot_id"], "held_until": row["held_until"]}
        for row in db.execute("SELECT * FROM charger_occupancies")
    ]


def charging_occupancies(db: sqlite3.Connection, now: float) -> list[dict[str, Any]]:
    """Only occupancies whose lease is still live, so the API never shows a ghost."""
    return [occupancy for occupancy in read_occupancies(db) if occupancy["held_until"] > now]


def read_chargers_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "position": {"x": row["x"], "y": row["y"]} if row["x"] is not None and row["y"] is not None else None,
    }


def claim_charger(db: sqlite3.Connection, lease: dict[str, Any], now: float) -> dict[str, Any] | None:
    """Occupy a charger inside the open transaction, or return the current holder."""
    db.execute("DELETE FROM charger_occupancies WHERE held_until <= ?", (now,))
    row = db.execute("SELECT robot_id FROM charger_occupancies WHERE charger_id = ?", (lease["charger_id"],)).fetchone()
    if row is not None and row["robot_id"] != lease["robot_id"]:
        return {"charger_id": lease["charger_id"], "robot_id": row["robot_id"]}
    db.execute(
        "INSERT INTO charger_occupancies(charger_id, robot_id, held_until) VALUES (?, ?, ?) "
        "ON CONFLICT(charger_id) DO UPDATE SET robot_id = excluded.robot_id, held_until = excluded.held_until",
        (lease["charger_id"], lease["robot_id"], lease["held_until"]),
    )
    return None


def release_charger(db: sqlite3.Connection, *, robot_id: str | None = None, charger_id: str | None = None) -> int:
    if robot_id is not None:
        return db.execute("DELETE FROM charger_occupancies WHERE robot_id = ?", (robot_id,)).rowcount
    if charger_id is not None:
        return db.execute("DELETE FROM charger_occupancies WHERE charger_id = ?", (charger_id,)).rowcount
    return 0


def charge_plan(robot_row: sqlite3.Row | None = None, now: float | None = None) -> dict[str, Any]:
    """Whether the robot should charge, and which charger it would get."""
    now = time.time() if now is None else now
    with connection() as db:
        if robot_row is None:
            return {"charge": False, "reason": "robot_not_found"}
        robot = robot_payload(robot_row, now)
        decision = charging.should_charge(robot["battery"], status=robot["status"])
        if not decision["charge"]:
            return {**decision, "charger": None}
        allocation = charging.rank_chargers(
            read_chargers(db), read_occupancies(db), robot_position=robot["position"], now=now,
        )
        return {**decision, "charger": allocation}


def dispatch_preview(mission_row: sqlite3.Row | None = None, origin: str | None = None) -> dict[str, Any]:
    with connection() as db:
        now = time.time()
        candidates = dispatch_candidates(db, now)
        resolved = origin_position(db, origin if origin is not None else (mission_row["origin"] if mission_row else ""))
    result = dispatch.rank_robots(candidates, origin_position=resolved)
    result["origin_position"] = resolved
    result["heartbeat_timeout_seconds"] = HEARTBEAT_TIMEOUT_SECONDS
    return result


def response_payload() -> dict[str, Any]:
    with connection() as db:
        missions = db.execute("SELECT * FROM missions ORDER BY id DESC LIMIT 10").fetchall()
        robots = db.execute("SELECT * FROM robots ORDER BY id").fetchall()
        active = db.execute("SELECT COUNT(*) FROM missions WHERE status IN ('running', 'waiting')").fetchone()[0]
    now = time.time()
    payloads = [robot_payload(row, now) for row in robots]
    online = sum(not item["stale"] for item in payloads)
    average_battery = round(sum(item["battery"] for item in payloads) / len(payloads)) if payloads else 0
    return {
        "fleet": {"online": online, "total": len(payloads), "utilization": None, "average_battery": average_battery},
        "robots": payloads,
        "missions": {"active": active, "cycle_minutes": None, "items": [mission_payload(row) for row in missions]},
        "system": {"core": None, "wms": None, "status": "prototype"},
        "heartbeat_timeout_seconds": HEARTBEAT_TIMEOUT_SECONDS,
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
        path = self.path.split("?", 1)[0]
        dispatch_get = DISPATCH_PATH.match(path)
        if dispatch_get:
            self.dispatch_mission(int(dispatch_get.group(1)))
            return
        charge_get = ROBOT_CHARGE_PATH.match(path)
        if charge_get:
            self.get_charge_plan(charge_get.group(1))
            return
        self.path = path
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
        elif self.path == "/api/chargers":
            self.get_chargers()
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
        if path == "/api/integrations/vda5050":
            self.receive_vda5050(payload)
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
        if path == "/api/chargers":
            self.add_charger(payload)
            return
        charge_post = ROBOT_CHARGE_PATH.match(path)
        if charge_post:
            self.start_charge(charge_post.group(1), payload)
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

    def receive_vda5050(self, payload: Any) -> None:
        """Inbound half of the VDA 5050 bridge.

        A gateway subscribed to ``state/{agv_id}`` and ``connection/{agv_id}``
        forwards messages here. Publishing orders back out is not wired yet, so
        this endpoint never claims a command reached a robot.
        """
        if not isinstance(payload, dict):
            self._send(422, {"error": "invalid_vda_message"})
            return
        agv_id = payload.get("agv_id")
        message_type = payload.get("message_type")
        body = payload.get("payload")
        if not isinstance(agv_id, str) or not agv_id.strip():
            self._send(422, {"error": "agv_id_is_required"})
            return
        if message_type not in {"state", "connection"}:
            self._send(422, {"error": "unsupported_message_type"})
            return

        if message_type == "connection":
            online = vda5050.connection_is_online(body)
            if online is None:
                self._send(422, {"error": "invalid_connection_message"})
                return
            with connection() as db:
                exists = db.execute("SELECT 1 FROM robots WHERE id = ?", (agv_id.strip(),)).fetchone()
                if not exists:
                    self._send(404, {"error": "robot_not_found"})
                    return
                # An explicit OFFLINE drops the heartbeat so the robot reads as
                # offline immediately instead of waiting for the timeout.
                if online:
                    db.execute("UPDATE robots SET heartbeat_at = ? WHERE id = ?", (time.time(), agv_id.strip()))
                else:
                    db.execute("UPDATE robots SET heartbeat_at = NULL WHERE id = ?", (agv_id.strip(),))
            self._send(200, {"accepted": True, "agv_id": agv_id.strip(), "online": online})
            return

        telemetry = vda5050.state_to_telemetry(body, MAP_EXTENT_METRES)
        if telemetry is None:
            self._send(422, {"error": "invalid_state_message"})
            return
        with connection() as db:
            exists = db.execute("SELECT 1 FROM robots WHERE id = ?", (agv_id.strip(),)).fetchone()
            if not exists:
                self._send(404, {"error": "robot_not_found"})
                return
            db.execute(
                """UPDATE robots SET status = ?, battery = ?, x = ?, y = ?, order_id = ?,
                   e_stop = ?, field_violation = ?, updated_at = CURRENT_TIMESTAMP, heartbeat_at = ?
                   WHERE id = ?""",
                (
                    telemetry["status"], telemetry["battery"], telemetry["position"]["x"],
                    telemetry["position"]["y"], telemetry["order_id"], telemetry["e_stop"],
                    int(telemetry["field_violation"]), time.time(), agv_id.strip(),
                ),
            )
            db.execute(
                "INSERT INTO telemetry_history(robot_id, status, battery, x, y) VALUES (?, ?, ?, ?, ?)",
                (agv_id.strip(), telemetry["status"], telemetry["battery"], telemetry["position"]["x"], telemetry["position"]["y"]),
            )
            if telemetry["status"] != "charging":
                release_charger(db, robot_id=agv_id.strip())
        self._send(200, {"accepted": True, "agv_id": agv_id.strip(), "telemetry": telemetry})

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
        now = time.time()
        with connection() as db:
            rows = db.execute("SELECT * FROM robots ORDER BY id").fetchall()
            missions = db.execute("SELECT id, origin, destination FROM missions WHERE status = 'waiting' ORDER BY id").fetchall()
            free = charging.free_chargers(read_chargers(db), read_occupancies(db), now)
        alerts = []
        for row in rows:
            robot = robot_payload(row, now)
            if robot["stale"]:
                alerts.append({"type": "robot_offline", "severity": "critical", "robot": robot["id"], "battery": robot["battery"]})
            elif robot["battery"] <= 20:
                # Say whether charging is actually achievable, not just that the
                # battery is low: a warning with no free bay is a dead end.
                decision = charging.should_charge(robot["battery"], status=robot["status"])
                alerts.append({
                    "type": "low_battery",
                    "severity": "warning",
                    "robot": robot["id"],
                    "battery": robot["battery"],
                    "charging_available": bool(free) and decision["charge"],
                    "charger": free[0]["id"] if free and decision["charge"] else None,
                })
            if robot["e_stop"] != "NONE":
                alerts.append({"type": "emergency_stop", "severity": "critical", "robot": robot["id"], "e_stop": robot["e_stop"]})
            if robot["field_violation"]:
                alerts.append({"type": "protective_field", "severity": "warning", "robot": robot["id"]})
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
        now = time.time()
        with connection() as db:
            nodes = [dict(row) for row in db.execute("SELECT * FROM map_nodes ORDER BY id")]
            edges = [dict(row) for row in db.execute("SELECT source, target FROM map_edges ORDER BY source, target")]
            obstacles = [row[0] for row in db.execute("SELECT node_id FROM map_obstacles WHERE active = 1")]
            reservations = traffic.active_reservations(read_reservations(db), now)
        self._send(200, {
            "nodes": nodes,
            "edges": edges,
            "obstacles": obstacles,
            "reservations": reservations,
            "conflicts": traffic.find_conflicts(reservations, now),
        })

    def add_map_node(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"].strip() or payload.get("kind") not in {"zone", "station"} or not isinstance(payload.get("name"), str) or not payload["name"].strip():
            self._send(422, {"error": "invalid_map_node"})
            return
        coords: dict[str, int | None] = {}
        for axis in ("x", "y"):
            value = payload.get(axis)
            if value is None:
                coords[axis] = None
            elif isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                self._send(422, {"error": "invalid_map_node_coordinates"})
                return
            else:
                coords[axis] = value
        if (coords["x"] is None) != (coords["y"] is None):
            # A single axis is not a location; reject rather than half-place it.
            self._send(422, {"error": "invalid_map_node_coordinates"})
            return
        node_id, name = payload["id"].strip(), payload["name"].strip()
        with connection() as db:
            if coords["x"] is None:
                # Preserve any coordinates already placed on this node.
                db.execute(
                    "INSERT INTO map_nodes(id, kind, name) VALUES (?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, name = excluded.name",
                    (node_id, payload["kind"], name),
                )
            else:
                db.execute(
                    "INSERT INTO map_nodes(id, kind, name, x, y) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, name = excluded.name, x = excluded.x, y = excluded.y",
                    (node_id, payload["kind"], name, coords["x"], coords["y"]),
                )
            row = db.execute("SELECT * FROM map_nodes WHERE id = ?", (node_id,)).fetchone()
        self._send(201, {"node": dict(row)})

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
        robot_id = payload.get("robot").strip() if isinstance(payload.get("robot"), str) else None
        reserve = payload.get("reserve") is True
        if reserve and not robot_id:
            self._send(422, {"error": "reserve_requires_robot"})
            return

        now = time.time()
        conflicts: list[dict[str, Any]] = []
        leased: list[str] = []
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = route_between(db, payload["start"], payload["goal"], robot_id=robot_id, now=now)
            if result["path"] and reserve:
                leases = traffic.lease_path(result["path"], robot_id=robot_id, mission_id=None, now=now)
                conflicts = claim_reservations(db, leases, now)
                if not conflicts:
                    leased = [lease["node_id"] for lease in leases]

        if conflicts:
            self._send(409, {"error": "traffic_conflict", "conflicts": conflicts})
            return
        if not result["path"]:
            error = "blocked_by_traffic" if result["status"] == "blocked_by_traffic" else "route_not_found"
            self._send(409, {"error": error, "traffic": result})
            return
        response: dict[str, Any] = {"path": result["path"], "traffic": result}
        if leased:
            response["leased_nodes"] = leased
        self._send(200, response)

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
        body = payload if isinstance(payload, dict) else {}
        auto = body.get("auto") is True
        robot_id = body.get("robot")
        if not auto and (not isinstance(robot_id, str) or not robot_id.strip()):
            self._send(422, {"error": "robot_id_is_required"})
            return
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            mission = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
            if mission is None:
                self._send(404, {"error": "mission_not_found"})
                return
            if mission["status"] not in {"waiting", "cancelled"}:
                self._send(409, {"error": "mission_not_assignable"})
                return
            dispatch_result = None
            if auto:
                dispatch_result = self._rank_for(db, mission["origin"])
                if dispatch_result["selected"] is None:
                    self._send(409, {"error": "no_eligible_robot", "dispatch": dispatch_result})
                    return
                robot_id = dispatch_result["selected"]
            robot = db.execute("SELECT * FROM robots WHERE id = ?", (robot_id.strip(),)).fetchone()
            if robot is None:
                self._send(422, {"error": "robot_not_found"})
                return
            if robot_payload(robot)["status"] == "offline":
                self._send(409, {"error": "robot_offline"})
                return
            db.execute("UPDATE missions SET robot = ?, status = 'running', started_at = 'اکنون' WHERE id = ?", (robot["id"], mission_id))
            row = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
            traffic_result = lease_mission_route(db, mission_id, robot["id"], mission["origin"], mission["destination"], time.time())
        response: dict[str, Any] = {"mission": mission_payload(row)}
        if dispatch_result is not None:
            response["dispatch"] = dispatch_result
        if traffic_result is not None:
            response["traffic"] = traffic_result
        self._send(200, response)

    @staticmethod
    def _rank_for(db: sqlite3.Connection, origin: str) -> dict[str, Any]:
        """Rank robots against the live fleet, reusing the open transaction."""
        resolved = origin_position(db, origin)
        result = dispatch.rank_robots(dispatch_candidates(db), origin_position=resolved)
        result["origin_position"] = resolved
        return result

    def dispatch_mission(self, mission_id: int) -> None:
        """Dry-run: who would be chosen, and why, without assigning anything."""
        with connection() as db:
            mission = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
            if mission is None:
                self._send(404, {"error": "mission_not_found"})
                return
            if mission["status"] not in {"waiting", "cancelled"}:
                self._send(409, {"error": "mission_not_assignable"})
                return
            result = dispatch_preview(mission)
        self._send(200, {"mission": mission_payload(mission), "dispatch": result})

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
            released = release_reservations(db, mission_id=mission_id)
            row = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        self._send(200, {"mission": mission_payload(row), "released_nodes": released})

    def get_chargers(self) -> None:
        now = time.time()
        with connection() as db:
            chargers = read_chargers(db)
            occupancies = charging_occupancies(db, now)
        self._send(200, {"chargers": chargers, "occupancies": occupancies})

    def get_charge_plan(self, robot_id: str) -> None:
        with connection() as db:
            robot = db.execute("SELECT * FROM robots WHERE id = ?", (robot_id,)).fetchone()
        if robot is None:
            self._send(404, {"error": "robot_not_found"})
            return
        self._send(200, {"robot": robot_id, **charge_plan(robot)})

    def add_charger(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"].strip():
            self._send(422, {"error": "charger_id_required"})
            return
        name = payload.get("name", payload["id"])
        if not isinstance(name, str) or not name.strip():
            self._send(422, {"error": "invalid_charger_name"})
            return
        coords: dict[str, int | None] = {}
        for axis in ("x", "y"):
            value = payload.get(axis)
            if value is None:
                coords[axis] = None
            elif isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                self._send(422, {"error": "invalid_charger_coordinates"})
                return
            else:
                coords[axis] = value
        if (coords["x"] is None) != (coords["y"] is None):
            self._send(422, {"error": "invalid_charger_coordinates"})
            return
        charger_id = payload["id"].strip()
        with connection() as db:
            db.execute(
                "INSERT INTO chargers(id, name, x, y) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, x = COALESCE(excluded.x, chargers.x), y = COALESCE(excluded.y, chargers.y)",
                (charger_id, name.strip(), coords["x"], coords["y"]),
            )
            row = db.execute("SELECT * FROM chargers WHERE id = ?", (charger_id,)).fetchone()
        self._send(201, {"charger": read_chargers_row(row)})

    def start_charge(self, robot_id: str, payload: Any) -> None:
        """Send a robot to a charger, honouring the charger's single occupant."""
        body = payload if isinstance(payload, dict) else {}
        requested = body.get("charger")
        if requested is not None and (not isinstance(requested, str) or not requested.strip()):
            self._send(422, {"error": "invalid_charger"})
            return
        now = time.time()
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            robot = db.execute("SELECT * FROM robots WHERE id = ?", (robot_id,)).fetchone()
            if robot is None:
                self._send(404, {"error": "robot_not_found"})
                return
            plan = charge_plan(robot, now)
            if not plan["charge"]:
                self._send(409, {"error": "charging_not_required", "plan": plan})
                return
            allocation = plan["charger"]
            if requested is not None:
                match = next((c for c in allocation["available"] if c["id"] == requested.strip()), None)
                if match is None:
                    self._send(409, {"error": "charger_unavailable", "plan": plan})
                    return
                allocation = {**allocation, "selected": requested.strip()}
            if allocation["selected"] is None:
                self._send(409, {"error": allocation["reason"] or "no_charger_available", "plan": plan})
                return
            lease = charging.lease_charger(allocation["selected"], robot["id"], now=now)
            conflict = claim_charger(db, lease, now)
            if conflict:
                self._send(409, {"error": "charger_busy", "conflict": conflict})
                return
            db.execute("UPDATE robots SET status = 'charging' WHERE id = ?", (robot["id"],))
            updated = db.execute("SELECT * FROM robots WHERE id = ?", (robot["id"],)).fetchone()
        self._send(200, {"robot": robot_payload(updated), "charger": allocation["selected"], "plan": allocation})

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
            cursor = db.execute(
                "UPDATE robots SET status = ?, battery = ?, x = ?, y = ?, updated_at = CURRENT_TIMESTAMP, heartbeat_at = ? WHERE id = ?",
                (status, battery, position["x"], position["y"], time.time(), payload["id"]),
            )
            if cursor.rowcount:
                db.execute("INSERT INTO telemetry_history(robot_id, status, battery, x, y) VALUES (?, ?, ?, ?, ?)", (payload["id"], status, battery, position["x"], position["y"]))
                if status != "charging":
                    # A robot that reports moving/waiting has left the bay; without
                    # this the charger stays blocked until its lease expires.
                    release_charger(db, robot_id=payload["id"])
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
