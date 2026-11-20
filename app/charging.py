"""Charger allocation for the fleet manager.

OEM fleet managers assign charging between jobs rather than only at exhaustion,
because that both protects battery life and keeps material moving. This module
answers two questions and nothing more:

- *When* should a robot be sent to charge, given its current charge and workload?
- *Which* charger should it get, when several robots want the same bay?

A charger holds at most one robot at a time, mirroring the corridor rule: the
database enforces a single holder. Allocation is not silent — every decision
carries the reason it was made, and a robot that cannot be served says so
instead of being parked forever.
"""

from __future__ import annotations

from typing import Any

# Send a robot to charge at or below this charge level.
CHARGE_THRESHOLD = 25
# Refuse to start a charge below this: the robot is stranded, not merely low.
CRITICAL_BATTERY = 5
# A charger whose lease is older than this is considered free again.
DEFAULT_CHARGE_LEASE_SECONDS = 1800.0

CHARGE_REASONS = {
    "idle_below_threshold": "idle with a low battery, so charging costs no throughput",
    "below_threshold": "battery at or below the charging threshold",
    "critical": "battery critically low",
}


def should_charge(battery: int | None, *, status: str, threshold: int = CHARGE_THRESHOLD) -> dict[str, Any]:
    """Decide whether a robot should be sent to charge, and why.

    ``status`` is the derived status, so a stale robot reads ``offline`` and is
    never told to charge — a robot that is not reporting cannot act on it.
    """
    if status in {"offline", "charging"}:
        return {"charge": False, "reason": f"status_{status}"}
    if not isinstance(battery, int) or isinstance(battery, bool):
        return {"charge": False, "reason": "battery_unknown"}
    if battery <= CRITICAL_BATTERY:
        return {"charge": True, "reason": "critical", "battery": battery}
    if battery <= threshold:
        # An idle robot is the cheapest to charge; a busy one still qualifies,
        # but the reason distinguishes the two so an operator can see why.
        reason = "idle_below_threshold" if status == "waiting" else "below_threshold"
        return {"charge": True, "reason": reason, "battery": battery}
    return {"charge": False, "reason": "battery_sufficient", "battery": battery}


def free_chargers(chargers: list[dict[str, Any]], occupancies: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Chargers with no active lease for any other robot."""
    busy = {
        occupancy.get("charger_id")
        for occupancy in occupancies
        if isinstance(occupancy.get("held_until"), (int, float))
        and not isinstance(occupancy.get("held_until"), bool)
        and occupancy["held_until"] > now
    }
    return [charger for charger in chargers if charger.get("id") not in busy]


def rank_chargers(
    chargers: list[dict[str, Any]],
    occupancies: list[dict[str, Any]],
    *,
    robot_position: dict[str, int] | None = None,
    now: float = 0.0,
) -> dict[str, Any]:
    """Pick the nearest free charger, and explain what happened to the rest.

    ``chargers`` entries carry ``id``, ``name`` and an optional ``position``.
    Distance is used only when both the charger and the robot have a placed
    position; otherwise chargers fall back to id order so the choice is still
    reproducible rather than arbitrary.
    """
    available = free_chargers(chargers, occupancies, now)
    ranked: list[dict[str, Any]] = []
    for charger in available:
        distance = _distance(robot_position, charger.get("position"))
        ranked.append({"id": charger.get("id"), "name": charger.get("name"), "distance": distance})

    # Known distances first, nearest first; unknown distance keeps id order.
    ranked.sort(key=lambda item: (item["distance"] is None, item["distance"] if item["distance"] is not None else 0.0, str(item["id"])))
    busy_ids = [c.get("id") for c in chargers if c.get("id") not in {r["id"] for r in available}]
    return {
        "selected": ranked[0]["id"] if ranked else None,
        "distance_used": any(item["distance"] is not None for item in ranked),
        "available": ranked,
        "busy": busy_ids,
        "reason": None if ranked else ("no_chargers_configured" if not chargers else "all_chargers_busy"),
    }


def _distance(left: Any, right: Any) -> float | None:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    values = []
    for point in (left, right):
        x, y = point.get("x"), point.get("y")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
            return None
        values.extend((x, y))
    return ((values[0] - values[2]) ** 2 + (values[1] - values[3]) ** 2) ** 0.5


def lease_charger(charger_id: str, robot_id: str, *, now: float, seconds: float = DEFAULT_CHARGE_LEASE_SECONDS) -> dict[str, Any] | None:
    """Build a charger occupancy record, or None for unusable input."""
    if not isinstance(charger_id, str) or not charger_id.strip():
        return None
    if not isinstance(robot_id, str) or not robot_id.strip():
        return None
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    return {
        "charger_id": charger_id.strip(),
        "robot_id": robot_id.strip(),
        "held_until": float(now) + float(seconds),
    }
