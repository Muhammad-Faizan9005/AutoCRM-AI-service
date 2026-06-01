from __future__ import annotations

import inspect
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.schemas.actions import AgentAction
from app.schemas.events import AgentEventIn
from app.services.action_manager import ActionManager
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
        context = await self.context_service.build_context(payload.entity_id, payload.entity_type)
        state["context"] = context
        return state

    def _action_node(self, action_factory):
        async def _node(state: WorkflowState) -> WorkflowState:
            payload = state["payload"]
            run_context = state["run_context"]
            context = state["context"]
            action = action_factory(payload, context)
            if inspect.isawaitable(action):
                action = await action
            state["action"] = action
            await self.action_manager.create_action(run_context.run_id, action)
            return state

        return _node
