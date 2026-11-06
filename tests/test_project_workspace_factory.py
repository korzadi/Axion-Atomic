import tempfile
import unittest
from pathlib import Path

from agent.project_workspace import project_workspace
from agent.workspace import PathViolation


class ProjectWorkspaceFactoryTests(unittest.TestCase):
    def test_binds_only_the_requested_existing_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "project_A"
            second = root / "project_B"
            first.mkdir()
            second.mkdir()
            (first / "marker.txt").write_text("A", encoding="utf-8")
            (second / "marker.txt").write_text("B", encoding="utf-8")

            workspace = project_workspace(root, "project_A")

            self.assertEqual(workspace.project_id, "project_A")
            self.assertEqual(workspace.read("marker.txt"), "A")
            self.assertEqual(workspace.root, first.resolve())

    def test_rejects_traversal_and_path_shaped_project_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            for project_id in ("../outside", "/tmp/project", "a/b", "a\\\\b", ""):
                with self.subTest(project_id=project_id):
                    with self.assertRaises(PathViolation):
                        project_workspace(tmp, project_id)

    def test_rejects_missing_project_directory_without_creating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PathViolation):
                project_workspace(tmp, "missing-project")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_rejects_symlinked_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspaces"
            outside = Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text("not for this project", encoding="utf-8")
            (root / "project_A").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(PathViolation):
                project_workspace(root, "project_A")


if __name__ == "__main__":
    unittest.main()
