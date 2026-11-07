"""Extrae los scripts inline de Axyron Atomic y valida sintaxis con Node.js."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile


class ScriptExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.parts = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.in_script = True
            self.parts = []

    def handle_data(self, data):
        if self.in_script:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_script:
            self.scripts.append("".join(self.parts))
            self.in_script = False
            self.parts = []


def main():
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    html = frontend / "Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html"
    parser = ScriptExtractor()
    parser.feed(html.read_text(encoding="utf-8"))
    if not parser.scripts:
        raise SystemExit("No se encontraron scripts inline en la página principal seleccionada")
    for index, script in enumerate(parser.scripts, start=1):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".js"
        ) as source:
            source.write(script)
            source.flush()
            subprocess.run(
                ["node", "--check", source.name],
                text=True,
                check=True,
            )
        print(f"Script inline {index}: sintaxis válida")
    workspace_script = frontend / "workspace.js"
    subprocess.run(["node", "--check", str(workspace_script)], text=True, check=True)
    print("Workspace JS: sintaxis válida")
    studio_script = frontend / "studio.js"
    subprocess.run(["node", "--check", str(studio_script)], text=True, check=True)
    print("Axyron Studio SPA JS: sintaxis válida")
    admin_script = frontend / "admin.js"
    subprocess.run(["node", "--check", str(admin_script)], text=True, check=True)
    print("Admin portal JS: sintaxis válida")


if __name__ == "__main__":
    main()
