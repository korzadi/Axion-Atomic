import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.project_workspace import build_project_toolset, project_workspace
from agent.workspace import PathViolation
from sandbox.backends import DockerBackend


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
            for project_id in ("../outside", "/tmp/project", "a/b", "a\\b", ""):
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

    def test_toolset_is_bound_to_one_project_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for project_id, marker in (("project_A", "A"), ("project_B", "B")):
                directory = root / project_id
                directory.mkdir()
                (directory / "marker.txt").write_text(marker, encoding="utf-8")

            workspace_a, tools_a = build_project_toolset(root, "project_A")
            workspace_b, tools_b = build_project_toolset(root, "project_B")

            self.assertIsNot(workspace_a, workspace_b)
            self.assertEqual(workspace_a.project_id, "project_A")
            self.assertEqual(workspace_b.project_id, "project_B")
            self.assertEqual(tools_a["read_file"].run({"path": "marker.txt"}), "A")
            self.assertEqual(tools_b["read_file"].run({"path": "marker.txt"}), "B")

    def test_toolset_rejects_non_container_execution_backend(self):
        class LocalLikeBackend:
            isolation = "none"

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "project_A").mkdir()
            with self.assertRaisesRegex(PathViolation, "contenedor"):
                build_project_toolset(tmp, "project_A", backend=LocalLikeBackend())

    def test_container_backend_is_passed_to_project_scoped_executor(self):
        backend = object.__new__(DockerBackend)

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "project_A").mkdir()
            with patch("sandbox.executor.SandboxExecutor") as executor:
                workspace, tools = build_project_toolset(
                    tmp, "project_A", backend=backend
                )

            executor.assert_called_once()
            self.assertIs(executor.call_args.kwargs["ws"], workspace)
            self.assertIs(executor.call_args.kwargs["backend"], backend)
            self.assertIn("run_tests", tools)


if __name__ == "__main__":
    unittest.main()
