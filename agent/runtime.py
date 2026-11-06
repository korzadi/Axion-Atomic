"""Composition root del runtime de AXION con aprobaciones y ejecuciones persistentes."""
from typing import Callable

from agent.approval_store import DbApprovalGate
from agent.coding_agent import Chat, CodingAgent
from agent.run_store import RunStore
from agent.toolset import Tool
from rag.meta import MetaStore


def build_coding_agent(
    chat: Chat,
    tools: dict[str, Tool],
    meta: MetaStore,
    *,
    max_steps: int = 12,
    obs_limit: int = 6000,
    on_event: Callable[[dict], None] | None = None,
) -> CodingAgent:
    """Construye AXION usando la misma conexión transaccional para gate y run store.

    La autorización de acceso al proyecto debe realizarse antes de llamar a run(),
    restore() o resume(); este factory no autentica usuarios ni concede permisos.
    """
    gate = DbApprovalGate(meta)
    store = RunStore(meta)
    return CodingAgent(
        chat=chat,
        tools=tools,
        gate=gate,
        max_steps=max_steps,
        obs_limit=obs_limit,
        on_event=on_event,
        run_store=store,
    )
