import tempfile
import unittest
from pathlib import Path

from agent.workspace import PathViolation, Workspace


class WorkspacePathConfinementTests(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.TemporaryDirectory()
        self.outside = tempfile.TemporaryDirectory()
        self.addCleanup(self.project.cleanup)
        self.addCleanup(self.outside.cleanup)
        self.root = Path(self.project.name)
        self.external_file = Path(self.outside.name) / "secret.txt"
        self.external_file.write_text("outside secret", encoding="utf-8")
        self.ws = Workspace(self.root, "project-test")

    def test_rejects_absolute_and_parent_traversal_paths(self):
        for path in ("/etc/passwd", "../secret.txt", "sub/../../secret.txt"):
            with self.subTest(path=path), self.assertRaises(PathViolation):
                self.ws.resolve(path)

    def test_rejects_symlink_that_targets_outside_project(self):
        link = self.root / "external-link"
        try:
            link.symlink_to(self.external_file)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        with self.assertRaises(PathViolation):
            self.ws.read("external-link")

    def test_rejects_write_through_symlink_that_targets_outside_project(self):
        link = self.root / "external-link"
        try:
            link.symlink_to(self.external_file)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        with self.assertRaises(PathViolation):
            self.ws.propose_write("external-link", "overwritten", "regression test")
        self.assertEqual(self.external_file.read_text(encoding="utf-8"), "outside secret")

    def test_allows_symlink_target_inside_project(self):
        target = self.root / "safe.txt"
        target.write_text("inside", encoding="utf-8")
        link = self.root / "inside-link"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        self.assertEqual(self.ws.read("inside-link"), "inside")


if __name__ == "__main__":
    unittest.main()
