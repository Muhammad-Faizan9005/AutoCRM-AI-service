from __future__ import annotations

from uuid import UUID

from app.services.autocrm_client import AutoCRMClient


_SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "secret",
    "recording_path",
    "transcript",
    "transcript_text",
    "email",
    "phone",
    "recording_url",
    "assemblyai_transcript_id",
}
_MAX_STRING_LENGTH = 600
_MAX_LIST_ITEMS = 5
_MAX_DICT_ITEMS = 20


def _safe_trace_value(value: object, *, depth: int = 0) -> object:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING_LENGTH else f"{value[:_MAX_STRING_LENGTH].rstrip()}..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        safe_items = [_safe_trace_value(item, depth=depth + 1) for item in value[:_MAX_LIST_ITEMS]]
        if len(value) > _MAX_LIST_ITEMS:
            safe_items.append(f"[{len(value) - _MAX_LIST_ITEMS} more items]")
        return safe_items
    if isinstance(value, dict):
        safe: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_DICT_ITEMS:
                safe["__truncated__"] = f"{len(value) - _MAX_DICT_ITEMS} more keys"
                break
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in _SENSITIVE_KEYS):
                safe[str(key)] = "[redacted]"
            else:
                safe[str(key)] = _safe_trace_value(item, depth=depth + 1)
        return safe
    return str(value)


class RunTraceService:
    def __init__(self) -> None:
        self.client = AutoCRMClient()

    async def record(
        self,
        run_id: UUID,
        step: str,
        *,
        status: str = "completed",
        payload: dict[str, object] | None = None,
    ) -> None:
        safe_payload = _safe_trace_value(payload or {})
        await self.client.create_run_trace(
            run_id,
            step=step,
            status=status,
            payload=safe_payload if isinstance(safe_payload, dict) else {"value": safe_payload},
        )

    async def list_for_run(self, run_id: UUID) -> list[dict[str, object]]:
        return await self.client.list_run_traces(run_id)
