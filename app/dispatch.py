"""Explainable robot selection for auto-dispatch.

Every competitor auto-assigns work; the differentiator here is that the choice
is explainable. Each candidate gets a per-component breakdown so an operator can
see why one robot won, instead of trusting a black box.

Scoring deliberately uses only signals the prototype actually has: battery,
current workload and (when the mission origin resolves to a located map node)
travel distance. It never invents a proximity signal the data cannot support.
"""

from __future__ import annotations

from typing import Any

from charging import CHARGE_THRESHOLD

# A robot at or below this charge should not receive new work. It is derived
# from the charging threshold on purpose: a robot that qualifies to charge but
# still accepts missions would keep deferring the charge dispatch itself says it
# needs. One point above, because charging is inclusive at the threshold.
MIN_DISPATCH_BATTERY = CHARGE_THRESHOLD + 1

WEIGHTS = {"battery": 0.4, "workload": 0.35, "distance": 0.25}

INELIGIBLE_STATUSES = {"offline", "charging"}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _distance(left: Any, right: Any) -> float | None:
    """Euclidean distance on the 0-100 grid, or None when coordinates are missing."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    coordinates = []
    for point in (left, right):
        x, y = point.get("x"), point.get("y")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
            return None
        coordinates.extend((x, y))
    return ((coordinates[0] - coordinates[2]) ** 2 + (coordinates[1] - coordinates[3]) ** 2) ** 0.5


def rank_robots(
    robots: list[dict[str, Any]],
    *,
    origin_position: dict[str, int] | None = None,
    min_battery: int = MIN_DISPATCH_BATTERY,
) -> dict[str, Any]:
    """Rank robots for a mission and explain every decision.

    ``robots`` entries carry: ``id``, ``status`` (derived, so stale robots read
    ``offline``), ``battery``, ``position`` and ``active_missions`` (how many
    missions the robot is already running).
    """
    candidates: list[dict[str, Any]] = []
    for robot in robots:
        candidate = {"id": robot.get("id"), "eligible": False, "score": None, "reason": None, "components": {}}
        status = robot.get("status")
        battery = robot.get("battery")

        if status in INELIGIBLE_STATUSES:
            candidate["reason"] = f"status_{status}"
        elif not isinstance(battery, int) or isinstance(battery, bool):
            candidate["reason"] = "battery_unknown"
        elif battery < min_battery:
            candidate["reason"] = "battery_below_threshold"
        else:
            components: dict[str, dict[str, float]] = {
                "battery": {"value": _clamp(battery / 100), "weight": WEIGHTS["battery"]},
                "workload": {
                    "value": _clamp(1 / (1 + max(0, int(robot.get("active_missions") or 0)))),
                    "weight": WEIGHTS["workload"],
                },
            }
            distance = _distance(robot.get("position"), origin_position)
            if distance is not None:
                components["distance"] = {"value": _clamp(1 / (1 + distance)), "weight": WEIGHTS["distance"]}
            total_weight = sum(component["weight"] for component in components.values())
            score = sum(component["value"] * component["weight"] for component in components.values()) / total_weight
            for component in components.values():
                component["contribution"] = round(component["value"] * component["weight"] / total_weight, 4)
                component["value"] = round(component["value"], 4)
            candidate.update(eligible=True, score=round(score, 4), components=components)
        candidates.append(candidate)

    # Highest score wins; ties break on robot id so the choice is reproducible.
    ranked = sorted(
        (c for c in candidates if c["eligible"]),
        key=lambda c: (-c["score"], str(c["id"])),
    )
    return {
        "selected": ranked[0]["id"] if ranked else None,
        "eligible_count": len(ranked),
        "distance_used": bool(origin_position) and any("distance" in c["components"] for c in ranked),
        "candidates": candidates,
    }
