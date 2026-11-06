"""Repository Analyzer: resumen estructural de un proyecto (lenguajes, manifiestos, puntos de entrada,
grafo de imports internos). Análisis estático ligero; no ejecuta código del proyecto."""
import ast
import json
import posixpath
import re
from collections import defaultdict

from agent.secrets import find_secrets
from agent.workspace import Workspace

LANGS = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript",
         ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++",
         ".cc": "C++", ".hpp": "C++", ".php": "PHP", ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".sol": "Solidity",
         ".rb": "Ruby", ".kt": "Kotlin", ".cs": "C#", ".sh": "Shell", ".md": "Markdown", ".yml": "YAML",
         ".yaml": "YAML", ".json": "JSON", ".toml": "TOML"}
MANIFESTS = {"requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "package.json", "go.mod", "Cargo.toml",
             "pom.xml", "build.gradle", "composer.json", "Gemfile", "Dockerfile", "docker-compose.yml",
             "compose.yaml", "Makefile", "foundry.toml", "hardhat.config.js", "hardhat.config.ts"}
ENTRY_NAMES = {"main.py", "__main__.py", "app.py", "manage.py", "index.js", "index.ts", "server.js", "main.go",
               "main.rs", "Main.java", "main.c", "main.cpp", "index.php"}
JS_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*|require\()\s*['"](\.{1,2}/[^'"]+)['"]""")
JS_SUFFIXES = ("", ".js", ".ts", ".jsx", ".tsx", ".mjs", "/index.js", "/index.ts", "/index.tsx")
MAX_FILE_BYTES = 1_000_000


def _py_modules(files: list[str]) -> dict[str, str]:
    mods = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        parts = f[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for i in range(len(parts)):            # registra también sin prefijos (src/, lib/)
            if parts[i:]:
                mods.setdefault(".".join(parts[i:]), f)
    return mods


def _py_imports(rel: str, source: str, mods: dict[str, str]) -> list[str] | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    pkg = rel[:-3].split("/")[:-1] if not rel.endswith("__init__.py") else rel[:-3].split("/")[:-1]
    found = set()

    def add(name: str, exact: bool = False) -> bool:
        parts = name.split(".")
        for n in range(len(parts) if exact else len(parts), 0, -1):
            target = mods.get(".".join(parts[:n]))
            if target:
                if target != rel:
                    found.add(target)
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                add(a.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = pkg[: len(pkg) - (node.level - 1)] if node.level - 1 <= len(pkg) else []
                base = ".".join(anchor + ([base] if base else []))
            resolved_sub = False
            for a in node.names:
                if base and mods.get(f"{base}.{a.name}"):       # 'from pkg import submodulo'
                    resolved_sub = add(f"{base}.{a.name}", True) or resolved_sub
                elif not base:
                    add(a.name)
            if base and not resolved_sub:                        # símbolos importados desde el módulo mismo
                add(base)
    return sorted(found)


def _js_imports(rel: str, source: str, fileset: set[str]) -> list[str]:
    out = set()
    for m in JS_IMPORT.finditer(source):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), m.group(1)))
        for suf in JS_SUFFIXES:
            if base + suf in fileset:
                out.add(base + suf); break
    return sorted(out)


def _deps(name: str, text: str) -> list[str]:
    try:
        if name == "package.json":
            d = json.loads(text)
            return sorted({*d.get("dependencies", {}), *d.get("devDependencies", {})})
        if name == "requirements.txt":
            return sorted({re.split(r"[=<>!~\[; ]", l.strip(), 1)[0] for l in text.splitlines()
                           if l.strip() and not l.startswith(("#", "-"))})
        if name == "go.mod":
            return sorted({l.split()[0] for l in text.splitlines() if re.match(r"^\s+[\w.-]+\.[\w./-]+\s+v", l)})
    except ValueError:
        return []
    return []


def analyze(ws: Workspace, max_files: int = 5000) -> dict:
    files = list(ws.walk(max_files))
    fileset = set(files)
    mods = _py_modules(files)
    langs: dict[str, dict] = defaultdict(lambda: {"files": 0, "lines": 0})
    manifests, entries, imports, parse_errors, secret_files, deps = [], [], {}, [], [], {}
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if name in MANIFESTS:
            manifests.append(rel)
        if name in ENTRY_NAMES:
            entries.append(rel)
        lang = LANGS.get(ext)
        path = ws.root / rel
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            continue
        raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        text = raw.decode("utf-8", "replace")
        if lang:
            langs[lang]["files"] += 1
            langs[lang]["lines"] += text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        if find_secrets(text):
            secret_files.append(rel)                     # solo la ruta, jamás el valor
        if name in ("package.json", "requirements.txt", "go.mod"):
            deps[rel] = _deps(name, text)
        if ext == ".py":
            res = _py_imports(rel, text, mods)
            if res is None:
                parse_errors.append(rel)
            elif res:
                imports[rel] = res
        elif ext in (".js", ".jsx", ".mjs", ".ts", ".tsx"):
            res = _js_imports(rel, text, fileset)
            if res:
                imports[rel] = res
    top = sorted({f.split("/")[0] for f in files if "/" in f})
    return {"total_files": len(files), "truncated": len(files) >= max_files,
            "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1]["lines"])),
            "manifests": manifests, "entry_points": entries, "top_dirs": top, "dependencies": deps,
            "imports": imports, "python_parse_errors": parse_errors, "files_with_possible_secrets": secret_files}


def render(summary: dict, max_chars: int = 4000) -> str:
    lines = [f"Archivos: {summary['total_files']}" + (" (truncado)" if summary["truncated"] else "")]
    lines.append("Lenguajes: " + ", ".join(f"{k} ({v['files']} archivos, {v['lines']} líneas)" for k, v in summary["languages"].items()))
    for key, label in (("manifests", "Manifiestos"), ("entry_points", "Puntos de entrada"), ("top_dirs", "Directorios")):
        if summary[key]:
            lines.append(f"{label}: " + ", ".join(summary[key]))
    for f, d in summary["dependencies"].items():
        lines.append(f"Dependencias {f}: " + ", ".join(d[:30]))
    if summary["files_with_possible_secrets"]:
        lines.append("ATENCIÓN posibles secretos en: " + ", ".join(summary["files_with_possible_secrets"]))
    if summary["python_parse_errors"]:
        lines.append("Python con errores de sintaxis: " + ", ".join(summary["python_parse_errors"]))
    lines.append("Imports internos:")
    for f, deps in summary["imports"].items():
        lines.append(f"  {f} -> {', '.join(deps)}")
    out = "\n".join(lines)
    return out if len(out) <= max_chars else out[:max_chars] + "\n…(resumen truncado)"
