from __future__ import annotations

import inspect
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.schemas.actions import AgentAction
from app.schemas.events import AgentEventIn
from app.services.action_manager import ActionManager
from app.services.autocrm_client import AutoCRMClient
from app.services.context_service import ContextService
from app.services.run_manager import RunContext


class WorkflowState(TypedDict):
    payload: AgentEventIn
    run_context: RunContext
    context: dict[str, object]
    action: AgentAction | None


class GraphRunner:
    def __init__(self) -> None:
        self.context_service = ContextService()
        self.action_manager = ActionManager()
        self.client = AutoCRMClient()

    def build(self, action_factory):
        graph = StateGraph(WorkflowState)
        graph.add_node("build_context", self._context_node)
        graph.add_node("build_action", self._action_node(action_factory))
        graph.add_edge("build_context", "build_action")
        graph.add_edge("build_action", END)
        graph.set_entry_point("build_context")
        return graph.compile()

    async def _context_node(self, state: WorkflowState) -> WorkflowState:
        payload = state["payload"]
        run_context = state["run_context"]
        await self.client.create_run_trace(
            run_id=run_context.backend_run_id,
            step="build_context",
            status="started",
            payload={"entity_type": payload.entity_type, "entity_id": str(payload.entity_id)},
        )
        try:
            context = await self.context_service.build_context(
                payload.entity_id,
                payload.entity_type,
                event_type=payload.event_type,
                metadata=payload.metadata or {},
            )
            state["context"] = context
            await self.client.create_run_trace(
                run_id=run_context.backend_run_id,
                step="build_context",
                status="completed",
                payload={
                    "context_keys": list(context.keys()),
                    "retrieval_query": context.get("retrieval_query"),
                    "rag_doc_count": len(context.get("rag_docs") or []),
                    "rag_sources": sorted(
                        {
                            str(doc.get("source") or "")
                            for doc in context.get("rag_docs") or []
                            if isinstance(doc, dict)
                        }
                    ),
                },
            )
            return state
        except Exception as exc:
            await self.client.create_run_trace(
                run_id=run_context.backend_run_id,
                step="build_context",
                status="failed",
                payload={"error": str(exc)},
            )
            raise

    def _action_node(self, action_factory):
        async def _node(state: WorkflowState) -> WorkflowState:
            payload = state["payload"]
            run_context = state["run_context"]
            context = state["context"]
            await self.client.create_run_trace(
                run_id=run_context.backend_run_id,
                step="build_action",
                status="started",
                payload={},
            )
            try:
                action = action_factory(payload, context)
                if inspect.isawaitable(action):
                    action = await action
                state["action"] = action
                if action is None:
                    await self.client.create_run_trace(
                        run_id=run_context.backend_run_id,
                        step="build_action",
                        status="completed",
                        payload={"decision": "no_action", "reason": "No actionable meeting items were found."},
                    )
                    return state

                await self.client.create_run_trace(
                    run_id=run_context.backend_run_id,
                    step="build_action",
                    status="completed",
                    payload={
                        "action_type": action.action_type,
                        "entity_type": action.entity_type,
                        "entity_id": str(action.entity_id),
                        "requires_approval": action.requires_approval,
                    },
                )
                await self.client.create_run_trace(
                    run_id=run_context.backend_run_id,
                    step="dispatch_action",
                    status="started",
                    payload={"action_type": action.action_type},
                )
                action_id = await self.action_manager.create_action(run_context.run_id, action)
                await self.client.create_run_trace(
                    run_id=run_context.backend_run_id,
                    step="dispatch_action",
                    status="completed",
                    payload={"action_id": str(action_id)},
                )
                return state
            except Exception as exc:
                await self.client.create_run_trace(
                    run_id=run_context.backend_run_id,
                    step="build_or_dispatch_action",
                    status="failed",
                    payload={"error": str(exc)},
                )
                raise

        return _node
