import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from api import project_creation


class FakeConnection:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if self.fail_on == len(self.calls):
            raise RuntimeError("database failure")
        return object()


class FakeEngine:
    def __init__(self, fail_on=None, fail_commit=False):
        self.connection = FakeConnection(fail_on)
        self.fail_commit = fail_commit

    @contextmanager
    def begin(self):
        yield self.connection
        if self.fail_commit:
            raise RuntimeError("commit failure")


class ProjectCreationTests(unittest.TestCase):
    def test_creates_project_owner_and_private_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeEngine()
            with (
                patch.object(project_creation, "engine", fake),
                patch.object(project_creation.settings, "workspace_root", tmp),
            ):
                result = project_creation.create_owned_project_with_workspace(
                    "user-1", "Project Alpha"
                )
            workspace = Path(tmp) / result["id"]
            self.assertTrue(workspace.is_dir())
            self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
            self.assertEqual(len(fake.connection.calls), 2)
            self.assertEqual(result["role"], "owner")

    def test_database_failure_before_workspace_creation_leaves_no_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeEngine(fail_on=2)
            with (
                patch.object(project_creation, "engine", fake),
                patch.object(project_creation.settings, "workspace_root", tmp),
            ):
                with self.assertRaisesRegex(RuntimeError, "database failure"):
                    project_creation.create_owned_project_with_workspace(
                        "user-1", "Project Alpha"
                    )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_commit_failure_removes_only_empty_new_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeEngine(fail_commit=True)
            with (
                patch.object(project_creation, "engine", fake),
                patch.object(project_creation.settings, "workspace_root", tmp),
            ):
                with self.assertRaisesRegex(RuntimeError, "commit failure"):
                    project_creation.create_owned_project_with_workspace(
                        "user-1", "Project Alpha"
                    )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_workspace_collision_is_not_reused_or_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Force a predictable ID only for this collision test.
            collision_id = "collision-id"
            existing = Path(tmp) / collision_id
            existing.mkdir()
            marker = existing / "keep.txt"
            marker.write_text("preserve")
            fake = FakeEngine()
            with (
                patch.object(project_creation, "engine", fake),
                patch.object(project_creation.settings, "workspace_root", tmp),
                patch.object(project_creation.secrets, "token_urlsafe", side_effect=[collision_id, "member-id"]),
            ):
                with self.assertRaises(FileExistsError):
                    project_creation.create_owned_project_with_workspace(
                        "user-1", "Project Alpha"
                    )
            self.assertEqual(marker.read_text(), "preserve")

    def test_invalid_name_fails_before_database_access(self):
        fake = FakeEngine()
        with patch.object(project_creation, "engine", fake):
            with self.assertRaises(ValueError):
                project_creation.create_owned_project_with_workspace("user-1", "x")
        self.assertEqual(fake.connection.calls, [])


if __name__ == "__main__":
    unittest.main()
