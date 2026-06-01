from __future__ import annotations

import hashlib


def build_idempotency_key(trigger_type: str, entity_id: str, window_bucket: str) -> str:
    raw = f"{trigger_type}:{entity_id}:{window_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
