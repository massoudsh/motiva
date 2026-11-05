from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

EVENT_TYPES = {"transport_request.created", "mission.status_changed", "mission.completed"}


def validate_event(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("id"), str)
        and bool(payload["id"].strip())
        and isinstance(payload.get("type"), str)
        and payload["type"] in EVENT_TYPES
        and payload.get("version") == 1
        and isinstance(payload.get("occurred_at"), str)
        and isinstance(payload.get("data"), dict)
    )


def signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def valid_signature(body: bytes, supplied: str | None, secret: str) -> bool:
    return bool(supplied) and hmac.compare_digest(signature(body, secret), supplied)


def decode_event(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if validate_event(payload) else None
