"""Operations analytics for the console.

Every figure here is derived from rows the prototype actually stores
(missions, telemetry samples, robots). Nothing is extrapolated into a
metric the data cannot support, and the response says which signals were
used so the UI does not present an estimate as measured fact.
"""

from __future__ import annotations

from typing import Any

ROBOT_STATUSES = ("moving", "waiting", "charging", "offline")


def summarize(
    *,
    mission_statuses: dict[str, int],
    throughput_rows: list[dict[str, Any]],
    busy_rows: list[dict[str, Any]],
    robot_count: int,
    days: int,
) -> dict[str, Any]:
    """Return the console summary. Units are named in the payload."""
    total_missions = sum(mission_statuses.values())
    completed = mission_statuses.get("done", 0)
    completion_rate = round(completed / total_missions * 100) if total_missions else None

    samples = sum(int(row.get("samples", 0)) for row in throughput_rows)
    busiest = [{"robot_id": row["robot_id"], "moving_samples": int(row.get("samples", 0))} for row in busy_rows]
    moving_samples = sum(item["moving_samples"] for item in busiest)
    # Estimated duty share: moving samples against every sample the fleet could
    # have produced in the window if each robot reported once per minute.
    capacity = max(1, robot_count) * max(1, days * 24 * 60)
    moving_share = round(moving_samples / capacity * 100, 1) if robot_count else None

    return {
        "days": days,
        "missions": {
            "by_status": mission_statuses,
            "total": total_missions,
            "completion_rate_percent": completion_rate,
        },
        "telemetry": {"samples": samples, "daily": throughput_rows},
        "fleet": {
            "robots": robot_count,
            "busiest": busiest,
            "moving_sample_share_percent": moving_share,
            "share_basis": "moving telemetry samples / (robots x minutes in window)",
        },
        "definitions": {
            "completion_rate_percent": "done / all missions, all time",
            "moving_sample_share_percent": "estimate from stored samples, not measured uptime",
        },
    }
