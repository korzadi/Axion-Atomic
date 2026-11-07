from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DockerBuildContextTests(unittest.TestCase):
    def test_build_context_excludes_secrets_and_runtime_data(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for pattern in (
            ".env",
            ".env.*",
            "**/.env",
            "**/*.pem",
            "**/*.key",
            "**/*.db",
            "**/*.dump",
            "backups/",
            "workspace/",
            "knowledge/",
            ".git/",
        ):
            self.assertIn(pattern, content)

    def test_build_context_keeps_required_application_sources(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for required in ("!.env.example",):
            self.assertIn(required, content)
        for forbidden in ("agent/\n", "api/\n", "frontend/\n", ".agents/skills/\n"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
