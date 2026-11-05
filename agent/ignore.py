"""Reglas de exclusión estilo .gitignore (subconjunto): comentarios, negación '!', dir-only 'x/',
anclado con '/', '*', '?', '**'. Limitación: solo el .gitignore de la raíz (no los anidados)."""
import re
from pathlib import Path

DEFAULT_EXCLUDES = [".git/", "node_modules/", "__pycache__/", ".venv/", "venv/", "dist/", "build/", "target/",
                    ".mypy_cache/", ".pytest_cache/", ".idea/", ".vscode/", "*.pyc", "*.min.js"]


def _translate(pat: str) -> str:
    i, out = 0, ""
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out += "(?:.*/)?"; i += 3; continue
        if pat.startswith("/**", i) and i + 3 == len(pat):
            out += "/.*"; i += 3; continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return out


class IgnoreRules:
    def __init__(self, lines: list[str]):
        self.rules: list[tuple[re.Pattern, bool, bool]] = []  # (regex, negate, dir_only)
        for raw in lines:
            line = raw.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            neg = line.startswith("!")
            if neg:
                line = line[1:]
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = "/" in line
            line = line.lstrip("/")
            body = _translate(line)
            rx = re.compile(("^" if anchored else "^(?:.*/)?") + body + "$")
            self.rules.append((rx, neg, dir_only))

    @classmethod
    def for_root(cls, root: Path) -> "IgnoreRules":
        lines = list(DEFAULT_EXCLUDES)
        for name in (".gitignore", ".axionignore"):
            p = root / name
            if p.is_file():
                lines += p.read_text(encoding="utf-8", errors="replace").splitlines()
        return cls(lines)

    def _match(self, rel: str, is_dir: bool) -> bool:
        ignored = False
        for rx, neg, dir_only in self.rules:
            if dir_only and not is_dir:
                continue
            if rx.match(rel):
                ignored = not neg
        return ignored

    def is_ignored(self, rel: str, is_dir: bool = False) -> bool:
        parts = rel.strip("/").split("/")
        for i in range(1, len(parts)):          # si un directorio padre está ignorado, todo su contenido también
            if self._match("/".join(parts[:i]), True):
                return True
        return self._match("/".join(parts), is_dir)
