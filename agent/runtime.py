"""Composition root del runtime de AXION con stores persistentes."""
from typing import Callable

from agent.approval_store import DbApprovalGate
from agent.coding_agent import Chat, CodingAgent
from agent.run_store import RunStore
from agent.sqlalchemy_meta import SqlAlchemyMetaStore
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
    """Construye el agente; la autorización del proyecto debe ocurrir antes."""
    return CodingAgent(
        chat=chat,
        tools=tools,
        gate=DbApprovalGate(meta),
        max_steps=max_steps,
        obs_limit=obs_limit,
        on_event=on_event,
        run_store=RunStore(meta),
    )


def build_coding_agent_from_engine(
    chat: Chat,
    tools: dict[str, Tool],
    engine,
    *,
    max_steps: int = 12,
    obs_limit: int = 6000,
    on_event: Callable[[dict], None] | None = None,
) -> CodingAgent:
    """Construye stores con conexiones de pool por operación.

    No autentica ni autoriza, no crea workspaces y no activa endpoints HTTP.
    Las herramientas deben estar confinadas al proyecto autorizado.
    """
    meta = SqlAlchemyMetaStore(engine)
    return build_coding_agent(
        chat, tools, meta, max_steps=max_steps, obs_limit=obs_limit, on_event=on_event
    )
