import os
import stat
import tempfile
import unittest
from pathlib import Path

from agent.workspace import PathViolation
from api.project_workspace_provisioning import provision_project_workspace


class ProjectWorkspaceProvisioningTests(unittest.TestCase):
    def test_creates_private_child_under_existing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = provision_project_workspace(root, "project_123")
            self.assertEqual(workspace, root / "project_123")
            self.assertTrue(workspace.is_dir())
            self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o700)

    def test_existing_real_directory_is_reused_without_changing_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "project_123"
            existing.mkdir(mode=0o750)
            before = stat.S_IMODE(existing.stat().st_mode)
            self.assertEqual(provision_project_workspace(root, "project_123"), existing)
            self.assertEqual(stat.S_IMODE(existing.stat().st_mode), before)

    def test_rejects_path_shaped_project_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("../outside", "/tmp/x", "a/b", "a\\b", ""):
                with self.subTest(value=value):
                    with self.assertRaises(PathViolation):
                        provision_project_workspace(tmp, value)

    def test_rejects_symlink_at_project_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            outside = Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "project_123").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(PathViolation):
                provision_project_workspace(root, "project_123")

    def test_does_not_create_a_missing_workspace_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-created"
            with self.assertRaises(FileNotFoundError):
                provision_project_workspace(missing, "project_123")
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
