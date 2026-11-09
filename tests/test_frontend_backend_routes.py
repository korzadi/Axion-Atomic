"""Contrato frontend ↔ backend.

Cada literal de ruta API referenciada por el HTML principal, studio.js,
workspace.js y admin.js debe corresponder a una ruta registrada en la app
FastAPI (exacta, prefijo con parámetros dinámicos, o fragmento sufijo usado
en concatenación de rutas). Los archivos estáticos y assets se excluyen.
"""
import re
from pathlib import Path

from api.main import app

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_FILES = [
    ROOT / "frontend" / "Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html",
    ROOT / "frontend" / "studio.js",
    ROOT / "frontend" / "workspace.js",
    ROOT / "frontend" / "admin.js",
    ROOT / "frontend" / "sso-start.html",
    ROOT / "studio" / "index.html",
    ROOT / "studio" / "app.js",
] + sorted(ROOT.glob("frontend/*.html"))

STUDIO_CLIENT_ROUTES = {
    "/agent", "/buy", "/code", "/dashboard", "/knowledge", "/models", "/projects",
    "/usage", "/account", "/security", "/privacy", "/integrations", "/tools",
    "/sso", "/sso/callback", "/api",
}
STATIC_ASSETS = {
    "/studio.js",
    "/studio.css",
    "/workspace.js",
    "/admin.js",
    "/favicon.ico",
    "/modelos.html",
    "/funciones.html",
    "/como.html",
    "/demo.html",
    "/seguridad.html",
    "/precios.html",
    "/faq.html",
    "/sso-start",
    "/app.js",
}
LITERAL = re.compile(r"""["'](/[A-Za-z0-9_{-][^"'\s]{0,158})["']""")


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _route_paths() -> list[str]:
    return sorted({getattr(route, "path", "") for route in app.routes if getattr(route, "path", None)})


def _frontend_literals() -> list[tuple[str, str]]:
    literals = []
    for file in FRONTEND_FILES:
        source = file.read_text(encoding="utf-8")
        for match in LITERAL.finditer(source):
            raw = match.group(1).split("?", 1)[0].rstrip("/")
            if raw and not raw.startswith(("/v1", "//")):
                literals.append((file.name, raw))
            elif raw:
                literals.append((file.name, raw))
    return sorted(set(literals))


def _matches_exact_or_prefix(frontend: str, route: str) -> bool:
    fs, rs = _segments(frontend), _segments(route)
    if len(fs) > len(rs):
        return False
    for index, segment in enumerate(fs):
        if rs[index] != segment and not rs[index].startswith("{"):
            return False
    return True


def _matches_suffix_fragment(frontend: str, route: str) -> bool:
    fs, rs = _segments(frontend), _segments(route)
    if not fs or len(fs) >= len(rs):
        return False
    return rs[-len(fs):] == fs


def test_every_frontend_api_literal_matches_a_registered_route():
    routes = _route_paths()
    failures = []
    for file_name, literal in _frontend_literals():
        if literal in STATIC_ASSETS:
            continue
        if literal in STUDIO_CLIENT_ROUTES:  # ruta del cliente de AXYRON Studio, no del backend
            continue
        if any(_matches_exact_or_prefix(literal, route) or _matches_suffix_fragment(literal, route) for route in routes):
            continue
        failures.append(f"{file_name}: {literal}")
    assert not failures, "Literales frontend sin ruta backend:\n" + "\n".join(failures)
