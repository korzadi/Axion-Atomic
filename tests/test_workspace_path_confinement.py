import tempfile
import unittest
from pathlib import Path

from agent.workspace import AccessDenied, PathViolation, Workspace


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

    def test_rejects_symlink_target_inside_project(self):
        target = self.root / "safe.txt"
        target.write_text("inside", encoding="utf-8")
        link = self.root / "inside-link"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        with self.assertRaises(PathViolation):
            self.ws.read("inside-link")

    def test_rejects_symlink_parent_directory(self):
        target_dir = Path(self.outside.name)
        link_dir = self.root / "linked-dir"
        try:
            link_dir.symlink_to(target_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        with self.assertRaises(PathViolation):
            self.ws.read("linked-dir/secret.txt")

    def test_list_dir_skips_symlinks(self):
        (self.root / "visible.txt").write_text("visible", encoding="utf-8")
        link = self.root / "linked-secret"
        try:
            link.symlink_to(self.external_file)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        names = {entry["name"] for entry in self.ws.list_dir(".")}
        self.assertIn("visible.txt", names)
        self.assertNotIn("linked-secret", names)

    def test_walk_and_search_do_not_follow_symlinks(self):
        (self.root / "visible.txt").write_text("needle visible", encoding="utf-8")
        link = self.root / "linked-secret"
        try:
            link.symlink_to(self.external_file)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema de archivos no permite crear symlinks")
        walked = list(self.ws.walk())
        self.assertIn("visible.txt", walked)
        self.assertNotIn("linked-secret", walked)
        results = self.ws.search("secret")
        self.assertFalse(any(item["path"] == "linked-secret" for item in results))

    def test_partial_line_read_obeys_global_byte_limit(self):
        (self.root / "large.txt").write_text("0123456789", encoding="utf-8")
        self.ws.max_read_bytes = 4
        with self.assertRaises(AccessDenied):
            self.ws.read("large.txt", start_line=1, end_line=1)


if __name__ == "__main__":
    unittest.main()
