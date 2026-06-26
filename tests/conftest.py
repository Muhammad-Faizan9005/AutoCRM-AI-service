from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if "asyncpg" not in sys.modules:
    class _UniqueViolationError(Exception):
        pass

    async def _create_pool(*args, **kwargs):
        raise RuntimeError("asyncpg is stubbed in tests")

    sys.modules["asyncpg"] = types.SimpleNamespace(
        Pool=object,
        UniqueViolationError=_UniqueViolationError,
        create_pool=_create_pool,
    )

if "langchain_core.documents" not in sys.modules:
    langchain_core_module = types.ModuleType("langchain_core")
    documents_module = types.ModuleType("langchain_core.documents")

    class Document:
        def __init__(self, page_content: str):
            self.page_content = page_content

    documents_module.Document = Document
    langchain_core_module.documents = documents_module
    sys.modules["langchain_core"] = langchain_core_module
    sys.modules["langchain_core.documents"] = documents_module

if "langgraph.graph" not in sys.modules:
    langgraph_module = types.ModuleType("langgraph")
    graph_module = types.ModuleType("langgraph.graph")

    END = "__END__"

    class _CompiledGraph:
        def __init__(self, nodes, edges, entry):
            self.nodes = nodes
            self.edges = edges
            self.entry = entry

        async def ainvoke(self, state):
            current = self.entry
            while current and current != END:
                state = await self.nodes[current](state)
                edge = self.edges.get(current)
                if isinstance(edge, tuple):
                    route_fn, route_map = edge
                    current = route_map[route_fn(state)]
                else:
                    current = edge
            return state

    class StateGraph:
        def __init__(self, _state_type):
            self.nodes = {}
            self.edges = {}
            self.entry = None

        def add_node(self, name, fn):
            self.nodes[name] = fn

        def add_edge(self, source, target):
            self.edges[source] = target

        def add_conditional_edges(self, source, route_fn, route_map):
            self.edges[source] = (route_fn, route_map)

        def set_entry_point(self, name):
            self.entry = name

        def compile(self):
            return _CompiledGraph(self.nodes, self.edges, self.entry)

    graph_module.END = END
    graph_module.StateGraph = StateGraph
    langgraph_module.graph = graph_module
    sys.modules["langgraph"] = langgraph_module
    sys.modules["langgraph.graph"] = graph_module

from app.services.run_manager import RunContext


@pytest.fixture
def sample_run_context() -> RunContext:
    return RunContext(
        run_id=uuid4(),
        backend_run_id=uuid4(),
        trigger_type="test",
        entity_id=uuid4(),
        entity_type="lead",
        idempotency_key="test-key",
    )
