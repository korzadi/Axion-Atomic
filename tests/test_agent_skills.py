import tempfile
import unittest
from pathlib import Path

from agent.skills import SkillRegistry
from agent.workspace import Workspace
from agent.git import GitManager
from agent.toolset import build_tools


class SkillRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skills = self.root / ".agents" / "skills"

    def test_discovers_standard_skill_and_reads_on_demand(self):
        skill = self.skills / "test-driven-development"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: test-driven-development\ndescription: Guides test-first implementation.\n---\n# TDD\nWrite a failing test first.\n",
            encoding="utf-8",
        )
        registry = SkillRegistry(self.root)
        self.assertIn("test-driven-development", registry.list_text())
        self.assertIn("Write a failing test first", registry.read_text("test-driven-development"))

    def test_discovers_nested_upstream_bundle_layout(self):
        skill = self.skills / "agent-skills-pack" / "skills" / "security-and-hardening"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\\nname: security-and-hardening\\ndescription: Security review workflow.\\n---\\n# Security\\n",
            encoding="utf-8",
        )
        registry = SkillRegistry(self.root)
        self.assertIn("security-and-hardening", registry.list_text())
        self.assertIn("# Security", registry.read_text("security-and-hardening"))

    def test_rejects_invalid_manifest_and_symlinked_skill(self):
        bad = self.skills / "bad"
        bad.mkdir(parents=True)
        (bad / "SKILL.md").write_text("---\nname: ../bad\ndescription: invalid\n---\n")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("---\nname: outside\ndescription: outside\n---\n")
        (self.skills / "linked").symlink_to(outside, target_is_directory=True)
        self.assertEqual(SkillRegistry(self.root).discover(), [])

    def test_skills_are_exposed_as_read_only_agent_tools(self):
        self.skills.mkdir(parents=True)
        ws = Workspace(self.root, "p1")
        tools = build_tools(ws, GitManager(ws))
        self.assertIn("list_skills", tools)
        self.assertIn("read_skill", tools)
        self.assertFalse(tools["list_skills"].mutating)
        self.assertFalse(tools["read_skill"].mutating)


if __name__ == "__main__":
    unittest.main()
