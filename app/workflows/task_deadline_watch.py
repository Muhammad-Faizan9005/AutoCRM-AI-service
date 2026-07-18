from __future__ import annotations

import hashlib
from uuid import UUID

from app.schemas.actions import AgentAction
from app.schemas.events import AgentEventIn
from app.services.action_manager import ActionManager
from app.services.autocrm_client import AutoCRMClient
from app.services.llm_service import LLMService
from app.services.run_manager import RunContext
from app.workflows.base import BaseWorkflow


class TaskDeadlineWatchWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        client = AutoCRMClient()
        action_manager = ActionManager()
        llm = LLMService()
        candidate = payload.metadata or {}

        await client.create_run_trace(
            run_context.backend_run_id,
            step="deadline_gate",
            status="completed",
            payload={
                "task_id": str(payload.entity_id),
                "severity": candidate.get("severity"),
                "is_customer_facing": candidate.get("is_customer_facing"),
                "should_use_llm": candidate.get("should_use_llm"),
                "cache_hit": bool(candidate.get("fresh_llm_output")),
            },
        )

        if not candidate.get("should_use_llm"):
            return
        if candidate.get("fresh_llm_output"):
            await client.create_run_trace(
                run_context.backend_run_id,
                step="deadline_llm",
                status="completed",
                payload={"decision": "cache_reused"},
            )
            return

        fallback = self._fallback_summary(candidate)
        summary = ""
        fallback_used = False
        try:
            summary = await llm.generate(
                workflow="task_deadline_watch",
                context=str(candidate),
                model_tier="small",
                prompt="",
            )
        except Exception as exc:
            fallback_used = True
            await client.create_run_trace(
                run_context.backend_run_id,
                step="deadline_llm",
                status="failed",
                payload={"error": str(exc), "fallback_used": True},
            )
        if not str(summary or "").strip():
            summary = fallback
            fallback_used = True

        summary = self._compact(summary)
        await client.record_task_deadline_alert(
            {
                "task_id": str(payload.entity_id),
                "alert_type": "ai_task_recovery_suggestion",
                "severity": str(candidate.get("severity") or "medium"),
                "recipient_id": str(candidate.get("assigned_to") or "") or None,
                "message": summary,
                "llm_cache_key": candidate.get("llm_cache_key"),
                "llm_output": summary,
                "fallback_used": fallback_used,
                "metadata": {
                    "event_type": "task_deadline_watch",
                    "rule": "severity>=medium AND is_customer_facing=true AND cache_miss",
                },
            }
        )
        await client.create_run_trace(
            run_context.backend_run_id,
            step="deadline_llm",
            status="completed",
            payload={"fallback_used": fallback_used, "summary": summary},
        )

        action = AgentAction(
            action_type="create_note",
            entity_type="task",
            entity_id=UUID(str(payload.entity_id)),
            reason="Task deadline recovery suggestion",
            data={
                "content": f"AI deadline recovery suggestion: {summary}",
                "actor_id": candidate.get("assigned_to") or candidate.get("owner_id"),
            },
            requires_approval=False,
            idempotency_key=self._note_idempotency_key(payload.entity_id, candidate),
        )
        action_id = await action_manager.create_action(run_context.run_id, action)
        await client.create_run_trace(
            run_context.backend_run_id,
            step="deadline_internal_note",
            status="completed",
            payload={"action_id": str(action_id), "approval_required": False},
        )

    @staticmethod
    def _note_idempotency_key(entity_id: object, candidate: dict[str, object]) -> str:
        """Build a deterministic idempotency key that fits the backend's 64-char cap.

        The backend's AgentActionIn schema limits idempotency_key to max_length=64.
        The old key embedded the full llm_cache_key (which itself contains the task
        UUID + severity + hash), producing ~130 chars and a 422 rejection. We use the
        candidate's context_hash instead — it already encodes task identity, severity,
        and content, so idempotency semantics are preserved. Falls back to a hash of
        llm_cache_key if context_hash is absent.
        """
        discriminator = candidate.get("context_hash")
        if not discriminator:
            cache_key = str(candidate.get("llm_cache_key") or "")
            discriminator = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        return f"tdn:{entity_id}:{discriminator}"

    @staticmethod
    def _fallback_summary(candidate: dict[str, object]) -> str:
        title = str(candidate.get("title") or "Untitled task")
        entity = str(candidate.get("entity_name") or "the linked CRM record")
        severity = str(candidate.get("severity") or "medium")
        return f"Task \"{title}\" is {severity} risk for {entity}. Review manually and update the next customer-facing step."

    @staticmethod
    def _compact(value: object) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > 600:
            return text[:597].rstrip() + "..."
        return text

