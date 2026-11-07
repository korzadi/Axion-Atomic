"""Registro de herramientas del agente. Cada herramienta declara su esquema; los argumentos se validan
estrictamente (claves desconocidas, tipos, tamaño). Las herramientas que modifican algo NO se ejecutan:
devuelven una propuesta + una función de aplicación que exige una aprobación ligada."""
from dataclasses import dataclass
from typing import Callable

from agent.approval_gate import ActionProposal, ApprovedAction
from agent.git import GitManager
from agent.repo import analyze, render
from agent.workspace import Workspace
from agent.skills import SkillRegistry

MAX_ARG_CHARS = 200_000
TYPES = {"str": str, "int": int, "bool": bool, "list": list}


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, tuple[str, bool]]          # nombre -> (tipo, requerido)
    run: Callable[[dict], object] | None = None      # puede devolver str o un awaitable
    propose: Callable[[dict], tuple[ActionProposal, Callable[[ApprovedAction], str]]] | None = None
    applied_label: str = "APLICADO"

    @property
    def mutating(self) -> bool:
        return self.propose is not None

    def signature(self) -> str:
        return ", ".join(f"{k}{'' if req else '?'}: {t}" for k, (t, req) in self.params.items())


def validate_args(tool: Tool, args) -> dict:
    if not isinstance(args, dict):
        raise ValueError("args debe ser un objeto JSON")
    unknown = set(args) - set(tool.params)
    if unknown:
        raise ValueError(f"Argumentos desconocidos: {sorted(unknown)}")
    for name, (tname, required) in tool.params.items():
        if name not in args:
            if required:
                raise ValueError(f"Falta el argumento obligatorio '{name}'")
            continue
        v = args[name]
        ok = isinstance(v, TYPES[tname]) and not (tname == "int" and isinstance(v, bool))
        if tname == "list":
            ok = ok and len(v) <= 1000 and all(isinstance(x, str) for x in v)
            if ok and sum(len(x) for x in v) > MAX_ARG_CHARS:
                ok = False
        if not ok:
            raise ValueError(f"'{name}' debe ser {tname} válido y estar dentro de los límites")
        if isinstance(v, str) and len(v) > MAX_ARG_CHARS:
            raise ValueError(f"'{name}' excede el tamaño máximo")
    return args


def build_tools(ws: Workspace, git: GitManager, sandbox=None, skill_roots=()) -> dict[str, Tool]:
    def fs(kind):
        def propose(a):
            if kind == "write":
                ch = ws.propose_write(a["path"], a["content"], a["reason"])
            elif kind == "edit":
                ch = ws.propose_edit(a["path"], a["old"], a["new"], a["reason"])
            else:
                ch = ws.propose_delete(a["path"], a["reason"])
            return ch.proposal, (lambda ap: ws.apply(ch, ap))
        return propose

    def commit(a):
        prop = git.propose_commit(a["message"], a["paths"], a["reason"])
        return prop, (lambda ap: git.apply_commit(a["message"], a["paths"], prop, ap))

    def branch(a):
        prop = git.propose_create_branch(a["name"], a["reason"])
        return prop, (lambda ap: git.apply_create_branch(a["name"], prop, ap))

    skills = SkillRegistry(ws.root, trusted_roots=skill_roots)
    S, I = "str", "int"
    tools = [
        Tool("list_dir", "Lista un directorio del proyecto", {"path": (S, False)},
             run=lambda a: "\n".join(f"{e['type']:4} {e['name']}" + (f" ({e['size']} bytes)" if e["size"] is not None else "")
                                     for e in ws.list_dir(a.get("path", "."))) or "(vacío)"),
        Tool("read_file", "Lee un archivo (con rango de líneas opcional)",
             {"path": (S, True), "start_line": (I, False), "end_line": (I, False)},
             run=lambda a: ws.read(a["path"], a.get("start_line"), a.get("end_line"))),
        Tool("search", "Busca texto literal en el proyecto", {"query": (S, True), "glob": (S, False)},
             run=lambda a: "\n".join(f"{h['path']}:{h['line']}: {h['text']}" for h in ws.search(a["query"], a.get("glob"))) or "(sin resultados)"),
        Tool("repo_summary", "Resumen estructural del proyecto", {}, run=lambda a: render(analyze(ws))),
        Tool("list_skills", "Descubre skills Agent Skills instaladas en .agents/skills o .agent/skills", {}, run=lambda a: skills.list_text()),
        Tool("read_skill", "Lee las instrucciones SKILL.md de una skill por su identificador; nunca ejecuta scripts incluidos", {"name": (S, True)}, run=lambda a: skills.read_text(a["name"])),
        Tool("git_status", "Estado del repositorio Git", {}, run=lambda a: git.status()),
        Tool("git_diff", "Diferencias sin confirmar", {"path": (S, False), "staged": ("bool", False)},
             run=lambda a: git.diff(a.get("path"), a.get("staged", False)) or "(sin cambios)"),
        Tool("git_log", "Últimos commits", {"limit": (I, False)}, run=lambda a: git.log(a.get("limit", 10))),
        Tool("write_file", "Crea o reemplaza un archivo completo", {"path": (S, True), "content": (S, True), "reason": (S, True)},
             propose=fs("write")),
        Tool("edit_file", "Reemplaza un fragmento único de un archivo", {"path": (S, True), "old": (S, True), "new": (S, True), "reason": (S, True)},
             propose=fs("edit")),
        Tool("delete_file", "Elimina un archivo", {"path": (S, True), "reason": (S, True)}, propose=fs("delete")),
        Tool("git_commit", "Confirma archivos concretos", {"message": (S, True), "paths": ("list", True), "reason": (S, True)},
             propose=commit),
        Tool("git_create_branch", "Crea y activa una rama", {"name": (S, True), "reason": (S, True)}, propose=branch),
    ]
    if sandbox is not None:
        from sandbox.executor import render_result
        from sandbox.policy import NeedsApproval

        async def run_sandboxed(a):
            try:
                return render_result(await sandbox.run_auto(a["command"]))
            except NeedsApproval as exc:
                raise ValueError(f"{exc} Usa la herramienta run_command_approved para solicitarlo.") from exc

        async def run_tests(a):
            res, summary = await sandbox.run_tests()
            head = ""
            if summary:
                head = (f"PRUEBAS ({summary.framework}): {summary.passed} ok, {summary.failed} fallidas, {summary.errors} errores, "
                        f"{summary.skipped} omitidas" + ("; fallan: " + ", ".join(summary.failures[:10]) if summary.failures else "") + "\n")
            return head + render_result(res)

        def command(a):
            prop, decision = sandbox.propose(a["command"], a["reason"])

            async def apply(ap):
                return render_result(await sandbox.apply(decision, ap))
            return prop, apply

        tools += [
            Tool("run_sandboxed", "Ejecuta pruebas/compilación/lectura en un sandbox sin red sobre una copia del proyecto",
                 {"command": (S, True)}, run=run_sandboxed),
            Tool("run_tests", "Detecta y ejecuta las pruebas del proyecto en el sandbox", {}, run=run_tests),
            Tool("run_command_approved", "Ejecuta en el sandbox un comando que requiere aprobación (instalaciones, red, otros)",
                 {"command": (S, True), "reason": (S, True)}, propose=command, applied_label="EJECUTADO"),
        ]
    return {t.name: t for t in tools}
