import sys
import tempfile
import unittest

from sandbox.runner import run_bounded


class BoundedRunnerTests(unittest.TestCase):
    def test_forwards_stdin_file_descriptor(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(b"hola sandbox")
            stream.seek(0)
            result = run_bounded(
                [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                None,
                {"PATH": "/usr/bin:/bin"},
                5,
                1024,
                stdin=stream,
            )

        self.assertFalse(result.timed_out)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "hola sandbox")


if __name__ == "__main__":
    unittest.main()
