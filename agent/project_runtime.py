"""Orquestación segura del agente persistente por proyecto.

No expone HTTP ni selecciona un backend inseguro por defecto. La capa HTTP debe
entregar una identidad obtenida de current_user; cada operación vuelve a validar
la membresía antes de resolver el workspace o restaurar una ejecución.
"""
from typing import Callable

from agent.runtime import build_coding_agent_from_engine
from api.agent_workspace import build_authorized_project_toolset


class ProjectAgentRuntime:
    """Fachada de start/restore/resume para una ejecución ligada a un proyecto."""

    def __init__(
        self,
        engine,
        chat,
        *,
        workspace_root: str,
        backend=None,
        limits=None,
        audit: Callable[[dict], None] | None = None,
        snapshot_dir: str | None = None,
        max_steps: int = 12,
        obs_limit: int = 6000,
        on_event: Callable[[dict], None] | None = None,
    ):
        self.engine = engine
        self.chat = chat
        self.workspace_root = workspace_root
        self.backend = backend
        self.limits = limits
        self.audit = audit
        self.snapshot_dir = snapshot_dir
        self.max_steps = max_steps
        self.obs_limit = obs_limit
        self.on_event = on_event

    def _agent(self, user: dict, project_id: str):
        # Esta función comprueba la identidad y la membresía ANTES de abrir
        # el workspace. El backend queda inactivo si no se inyecta uno Docker.
        _, tools = build_authorized_project_toolset(
            user,
            project_id,
            backend=self.backend,
            limits=self.limits,
            audit=self.audit,
            snapshot_dir=self.snapshot_dir,
            workspace_root=self.workspace_root,
        )
        return build_coding_agent_from_engine(
            self.chat,
            tools,
            self.engine,
            max_steps=self.max_steps,
            obs_limit=self.obs_limit,
            on_event=self.on_event,
        )

    async def start(self, user: dict, project_id: str, goal: str, context: str = ""):
        """Inicia una ejecución persistente después de autorizar el proyecto."""
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal es obligatorio")
        agent = self._agent(user, project_id)
        return await agent.run(goal.strip(), context=context, project_id=project_id)

    async def resume(self, user: dict, project_id: str, run_id: str):
        """Restaura por ID + proyecto y continúa según el estado persistido.

        Las acciones que estaban en estado running se convierten en
        needs_reconciliation por CodingAgent.restore y nunca se reejecutan.
        """
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id es obligatorio")
        agent = self._agent(user, project_id)
        run = agent.restore(run_id.strip(), project_id)
        if run.status == "awaiting_approval":
            return await agent.resume(run)
        if run.status == "running":
            return await agent.continue_run(run)
        return run
