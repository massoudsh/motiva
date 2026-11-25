"""Priority ordering for the material-transport mission queue.

Kept separate from the HTTP layer so the ordering rules can be tested
without a server, and so the dashboard and the dispatcher agree on one
definition of "next".
"""

from __future__ import annotations

from typing import Any

# Mirrors the priority vocabulary accepted by /api/missions. Lower sorts first.
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def mission_number(mission_id: str) -> int:
    digits = "".join(character for character in mission_id if character.isdigit())
    return int(digits) if digits else 0


def sort_key(mission: dict[str, Any]) -> tuple[int, str, int]:
    """Priority, then deadline, then creation order.

    A mission without a deadline sorts after one with a deadline at the same
    priority: an unknown due time is not evidence it is due first. `none`
    sorts after any real deadline because no digit string starts with 'n'
    beyond the placeholder used here.
    """
    priority = PRIORITY_RANK.get(str(mission.get("priority", "normal")), PRIORITY_RANK["normal"])
    deadline = mission.get("deadline")
    return (priority, deadline if isinstance(deadline, str) and deadline else "~", mission_number(str(mission.get("id", ""))))


def order_missions(missions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(missions, key=sort_key)
