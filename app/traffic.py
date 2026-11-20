"""Temporal node reservations for multi-robot traffic.

VDA 5050 standardises messages only and explicitly excludes traffic
coordination, so this is fleet-manager work, not something the protocol gives
us. A node has at most one holder at a time; a holder blocks other robots but
never itself. Reservations are leases with an expiry, because the prototype has
no continuous progress feed to release nodes as a robot passes them.

Every planning result states whether reservations actually shaped the route, so
a caller never infers coordination that did not happen.
"""

from __future__ import annotations

from typing import Any, Hashable, Iterable

from navigation import shortest_path

Node = Hashable

DEFAULT_LEASE_SECONDS = 90.0
DEFAULT_RESERVATION_DEPTH = 6


def active_reservations(reservations: Iterable[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Reservations whose lease has not expired."""
    active = []
    for reservation in reservations:
        held_until = reservation.get("held_until")
        if isinstance(held_until, bool) or not isinstance(held_until, (int, float)):
            continue
        if held_until > now:
            active.append(reservation)
    return active


def holders_by_node(reservations: Iterable[dict[str, Any]], now: float, *, exclude_robot: str | None = None) -> dict[Node, str]:
    """Map each currently reserved node to the robot holding it."""
    holders: dict[Node, str] = {}
    for reservation in active_reservations(reservations, now):
        robot_id = reservation.get("robot_id")
        if exclude_robot is not None and robot_id == exclude_robot:
            continue
        node_id = reservation.get("node_id")
        if node_id is None:
            continue
        holders[node_id] = robot_id
    return holders


def plan_route(
    edges: Iterable[tuple[Node, Node]],
    start: Node,
    goal: Node,
    *,
    blocked: Iterable[Node] = (),
    reservations: Iterable[dict[str, Any]] = (),
    robot_id: str | None = None,
    now: float = 0.0,
) -> dict[str, Any]:
    """Plan a route that avoids permanent obstacles and other robots' leases.

    The start and goal are never treated as blocked: ``shortest_path`` already
    exempts them, so a robot can always enter and leave its own endpoints.
    """
    permanent = set(blocked)
    held = holders_by_node(reservations, now, exclude_robot=robot_id)
    dynamic = {node for node in held if node not in permanent}

    path = shortest_path(edges, start, goal, permanent | dynamic)
    if path:
        status = "detoured" if dynamic else "clear"
    else:
        # Distinguish "the map has no route" from "other robots are in the way".
        status = "blocked_by_traffic" if dynamic and shortest_path(edges, start, goal, permanent) else "no_route"

    return {
        "path": path,
        "status": status,
        "blocked_nodes": sorted((str(node) for node in dynamic)),
        "reserved_by": {str(node): held[node] for node in dynamic},
        "traffic_applied": bool(dynamic),
    }


def lease_path(
    path: list[Node],
    *,
    robot_id: str,
    mission_id: int,
    now: float,
    depth: int = DEFAULT_RESERVATION_DEPTH,
    seconds: float = DEFAULT_LEASE_SECONDS,
) -> list[dict[str, Any]]:
    """Lease the next few nodes of a path for one robot.

    Depth is bounded because a lease with no progress feed would otherwise hold
    an entire route indefinitely.
    """
    if not path or not isinstance(robot_id, str) or not robot_id.strip():
        return []
    if isinstance(depth, bool) or not isinstance(depth, int) or depth <= 0:
        return []
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return []
    return [
        {
            "node_id": node,
            "robot_id": robot_id,
            "mission_id": mission_id,
            "held_until": float(now) + float(seconds),
        }
        for node in path[:depth]
    ]


def find_conflicts(reservations: Iterable[dict[str, Any]], now: float, robot_id: str | None = None) -> list[dict[str, Any]]:
    """Nodes currently held by more than one robot.

    The storage layer enforces a single holder per node, so this is a guard
    against inconsistent data rather than an expected state.
    """
    seen: dict[Node, list[str]] = {}
    for reservation in active_reservations(reservations, now):
        node_id, holder = reservation.get("node_id"), reservation.get("robot_id")
        if node_id is None:
            continue
        seen.setdefault(node_id, []).append(holder)
    conflicts = [
        {"node_id": node, "robots": robots}
        for node, robots in seen.items()
        if len(robots) > 1 and (robot_id is None or robot_id in robots)
    ]
    return sorted(conflicts, key=lambda conflict: str(conflict["node_id"]))
