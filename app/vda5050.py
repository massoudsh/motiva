"""VDA 5050 translation for the Motiva fleet manager.

VDA 5050 standardises only the message contract between a master control and a
vehicle: transport orders, cyclic state, instant actions and connection
monitoring over MQTT. It deliberately excludes traffic coordination, routing,
reading person detection, charging curves and load handling, so this module
translates messages only. It never invents a capability the standard does not
carry.

The functions are pure so they can be tested without an MQTT broker.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAP_EXTENT_METRES = 100.0

ONLINE_STATES = {"ONLINE"}
OFFLINE_STATES = {"OFFLINE", "CONNECTIONBROKEN"}

# Actions still occupying the vehicle. FAILED/FINISHED no longer imply charging.
ACTIVE_ACTION_STATES = {"WAITING", "INITIALIZING", "RUNNING", "PAUSED"}


def _number(value: Any) -> float | None:
    """Return a finite float, rejecting booleans and non-numeric values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _clamp_percent(metres: float, extent: float) -> int:
    percent = round(metres / extent * 100)
    return max(0, min(100, percent))


def _charging(state: dict[str, Any]) -> bool:
    actions = state.get("actionStates")
    if not isinstance(actions, list):
        return False
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("actionType") == "startCharging" and action.get("actionStatus") in ACTIVE_ACTION_STATES:
            return True
    return False


def _order_active(state: dict[str, Any]) -> bool:
    """True while the vehicle still has an unfinished order."""
    order_id = state.get("orderId")
    if not isinstance(order_id, str) or not order_id.strip():
        return False
    last = state.get("lastNodeSequenceId")
    nodes = state.get("nodeStates")
    if isinstance(last, int) and not isinstance(last, bool) and isinstance(nodes, list) and nodes:
        sequences = [
            node["sequenceId"]
            for node in nodes
            if isinstance(node, dict)
            and isinstance(node.get("sequenceId"), int)
            and not isinstance(node.get("sequenceId"), bool)
        ]
        if sequences and last >= max(sequences):
            edges = state.get("edgeStates")
            if isinstance(edges, list):
                return any(isinstance(edge, dict) and not edge.get("released", True) for edge in edges)
            return False
    return True


def reported_status(state: dict[str, Any]) -> str:
    """Map a VDA state message onto Motiva's stored robot status.

    VDA 5050 does not normalise charging, so charging is only reported when the
    vehicle explicitly shows a running ``startCharging`` action.
    """
    if _charging(state):
        return "charging"
    if _order_active(state):
        return "moving"
    return "waiting"


def safety_flags(state: dict[str, Any]) -> dict[str, Any]:
    safety = state.get("safetyState")
    if not isinstance(safety, dict):
        return {"e_stop": "NONE", "field_violation": False}
    e_stop = safety.get("eStop")
    return {
        "e_stop": e_stop if e_stop in {"MANUAL", "REMOTE", "NONE"} else "NONE",
        "field_violation": bool(safety.get("fieldViolation")),
    }


def state_to_telemetry(state: Any, map_extent: float = DEFAULT_MAP_EXTENT_METRES) -> dict[str, Any] | None:
    """Convert a VDA state message into Motiva telemetry, or None if unusable.

    ``map_extent`` is the site size in metres that the dashboard's 0-100 grid
    covers; VDA coordinates are metres on the vehicle's own map.
    """
    if not isinstance(state, dict):
        return None
    extent = _number(map_extent)
    if extent is None or extent <= 0:
        return None

    battery_state = state.get("batteryState")
    position = state.get("agvPosition")
    if not isinstance(battery_state, dict) or not isinstance(position, dict):
        return None

    charge = _number(battery_state.get("batteryCharge"))
    x = _number(position.get("x"))
    y = _number(position.get("y"))
    if charge is None or not 0 <= charge <= 100 or x is None or y is None:
        return None

    errors = state.get("errors")
    order_id = state.get("orderId")
    operating_mode = state.get("operatingMode")
    return {
        "battery": round(charge),
        "status": reported_status(state),
        "position": {"x": _clamp_percent(x, extent), "y": _clamp_percent(y, extent)},
        "order_id": order_id if isinstance(order_id, str) else None,
        "operating_mode": operating_mode if isinstance(operating_mode, str) else None,
        "error_count": len(errors) if isinstance(errors, list) else 0,
        "position_initialized": bool(position.get("positionInitialized")),
        **safety_flags(state),
    }


def connection_is_online(connection: Any) -> bool | None:
    """Return True/False for a VDA connection message, None when unrecognised."""
    if not isinstance(connection, dict):
        return None
    state = connection.get("connectionState")
    if state in ONLINE_STATES:
        return True
    if state in OFFLINE_STATES:
        return False
    return None


def order_message(order_id: str, path: list[str], *, order_update_id: int = 0) -> dict[str, Any] | None:
    """Build a VDA order for a route of map node ids.

    This is the payload a gateway would publish on ``order/{agv_id}``. Building
    it does not dispatch anything: publishing is the remaining seam.
    """
    if not isinstance(order_id, str) or not order_id.strip():
        return None
    if not isinstance(path, list) or not path:
        return None
    nodes = [str(node) for node in path]
    if any(not node.strip() for node in nodes) or len(set(nodes)) != len(nodes):
        return None
    return {
        "orderId": order_id.strip(),
        "orderUpdateId": order_update_id,
        "nodes": [
            {"nodeId": node, "sequenceId": index, "released": True, "actions": []}
            for index, node in enumerate(nodes)
        ],
        "edges": [
            {"edgeId": f"{nodes[index]}->{nodes[index + 1]}", "sequenceId": index, "released": True, "actions": []}
            for index in range(len(nodes) - 1)
        ],
    }
