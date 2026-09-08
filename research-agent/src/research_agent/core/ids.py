from __future__ import annotations

from uuid import uuid4
from hashlib import sha256


def new_id(prefix: str) -> str:
    normalized = prefix.strip().upper().replace("_", "-")
    return f"{normalized}-{uuid4().hex[:10].upper()}"


def stable_id(prefix: str, *parts: object) -> str:
    normalized = prefix.strip().upper().replace("_", "-")
    payload = "\x1f".join(str(part).strip() for part in parts)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    return f"{normalized}-{digest}"

