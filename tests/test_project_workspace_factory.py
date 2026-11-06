import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.project_workspace import build_project_toolset, project_workspace
from agent.workspace import PathViolation
from sandbox.backends import DockerBackend


class ProjectWorkspaceFactoryTests(unittest.TestCase):
    def _private_dir(self, path: Path) -> None:
        path.mkdir(mode=0o700)
        path.chmod(0o700)

    def test_binds_only_the_requested_existing_private_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "project_A"
            second = root / "project_B"
            self._private_dir(first)
            self._private_dir(second)
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
            self._private_dir(root)
            self._private_dir(outside)
            (outside / "secret.txt").write_text("not for this project", encoding="utf-8")
            (root / "project_A").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(PathViolation):
                project_workspace(root, "project_A")

    def test_rejects_group_or_world_accessible_workspace_without_chmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / "project_A"
            workspace_dir.mkdir(mode=0o755)
            workspace_dir.chmod(0o755)
            with self.assertRaisesRegex(PathViolation, "permisos privados"):
                project_workspace(root, "project_A")
            self.assertEqual(workspace_dir.stat().st_mode & 0o777, 0o755)

    def test_accepts_more_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / "project_A"
            self._private_dir(workspace_dir)
            workspace_dir.chmod(0o500)
            self.assertEqual(project_workspace(root, "project_A").root, workspace_dir)

    def test_toolset_is_bound_to_one_project_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for project_id, marker in (("project_A", "A"), ("project_B", "B")):
                directory = root / project_id
                self._private_dir(directory)
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
            self._private_dir(Path(tmp) / "project_A")
            with self.assertRaisesRegex(PathViolation, "contenedor"):
                build_project_toolset(tmp, "project_A", backend=LocalLikeBackend())

    def test_container_backend_is_passed_to_project_scoped_executor(self):
        backend = object.__new__(DockerBackend)

        with tempfile.TemporaryDirectory() as tmp:
            self._private_dir(Path(tmp) / "project_A")
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
