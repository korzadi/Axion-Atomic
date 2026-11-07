"""Descubrimiento seguro del estándar Agent Skills por proyecto."""
import re
from pathlib import Path
from agent.secrets import redact

_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MAX_SKILLS = 100
_MAX_SKILL_BYTES = 64000
_MAX_ACTIVE_CHARS = 20000


class SkillRegistry:
    """Lee SKILL.md bajo .agents/skills o .agent/skills sin seguir symlinks."""

    def __init__(self, workspace_root):
        self.root = Path(workspace_root).resolve()

    def _roots(self):
        for relative in (".agents/skills", ".agent/skills"):
            path = self.root / relative
            if path.is_symlink() or not path.exists():
                continue
            resolved = path.resolve()
            if resolved == self.root or self.root not in resolved.parents or not resolved.is_dir():
                continue
            yield resolved

    @staticmethod
    def _manifest(path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_SKILL_BYTES:
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
        if not raw.startswith("---\n"):
            return None
        end = raw.find("\n---", 4)
        if end < 0:
            return None
        fields = {}
        for line in raw[4:end].splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() in {"name", "description"}:
                fields[key.strip()] = value.strip().strip("'\"").strip()
        name, description = fields.get("name"), fields.get("description")
        if not name or not _NAME.fullmatch(name) or not description or len(description) > 500:
            return None
        return {"name": name, "description": description, "content": raw}

    def discover(self):
        found = {}
        for root in self._roots():
            try:
                children = sorted(root.iterdir(), key=lambda item: item.name)
            except OSError:
                continue
            for child in children:
                if len(found) >= _MAX_SKILLS:
                    return list(found.values())
                if child.is_symlink() or not child.is_dir():
                    continue
                item = self._manifest(child / "SKILL.md")
                if item and item["name"] not in found:
                    found[item["name"]] = item
        return list(found.values())

    def list_text(self):
        items = self.discover()
        if not items:
            return "No hay skills instaladas en .agents/skills ni .agent/skills."
        return "\n".join(f"- {item['name']}: {item['description']}" for item in items)

    def read_text(self, name):
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError("Identificador de skill inválido")
        for item in self.discover():
            if item["name"] == name:
                body = item["content"][:_MAX_ACTIVE_CHARS]
                if len(item["content"]) > _MAX_ACTIVE_CHARS:
                    body += "\n[contenido truncado por límite]"
                return redact(body)
        raise ValueError("Skill no encontrada o manifiesto no válido")
