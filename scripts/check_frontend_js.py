"""Extrae los scripts inline de AXION STUDIO y valida sintaxis con Node.js."""
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
    html = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    parser = ScriptExtractor()
    parser.feed(html.read_text(encoding="utf-8"))
    if not parser.scripts:
        raise SystemExit("No se encontraron scripts inline en frontend/index.html")
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


if __name__ == "__main__":
    main()
