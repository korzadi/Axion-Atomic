import unittest
from unittest import mock

from sandbox.backends import DockerBackend, LocalBackend, ResourceLimits, SandboxUnavailable, docker_argv
from sandbox.policy import classify

AUTO = ["python -m pytest -q", "pytest tests/", "python -m unittest discover", "python script.py", "python -c 'print(1)'", "go test ./...",
        "npm test", "npm run build", "cargo test", "gcc -o a main.c", "ls -la", "cat README.md", "grep -n foo src/a.py", "make test",
        "find . -name '*.py'", "echo 'a && b'", "node app.js"]
APPROVAL = ["pip install requests", "python -m pip install x", "npm install", "npm ci", "npx create-foo", "curl https://example.com", "bash run.sh",
            "./run.sh", "rm file.txt", "make deploy", "find . -delete", "unknowncmd --x", "mvn test", "python -m http.server", "go get x/y"]
BLOCKED = ["sudo ls", "rm -rf /", "cat /etc/passwd", "cat ../x", "ls ~", "ls | wc -l", "echo hi > f", "echo $(id)", "FOO=1 pytest", "/bin/ls",
           "", "   ", "git status", "docker run x", "python -m pytest --rootdir=/etc", "echo `id`", "ls && rm x", "chmod 777 a", "nc -l 80", "cat 'sin cierre"]


class PolicyTests(unittest.TestCase):
    def test_auto(self):
        for c in AUTO: self.assertEqual(classify(c).level, "auto", c)

    def test_approval(self):
        for c in APPROVAL: self.assertEqual(classify(c).level, "approval", c)

    def test_blocked(self):
        for c in BLOCKED: self.assertEqual(classify(c).level, "blocked", c)

    def test_network_flag_only_for_network_commands(self):
        self.assertTrue(classify("pip install x").network); self.assertTrue(classify("curl https://x").network)
        self.assertFalse(classify("bash run.sh").network); self.assertFalse(classify("rm a").network)

    def test_limits_on_size(self):
        self.assertEqual(classify("echo " + "a" * 3000).level, "blocked")
        self.assertEqual(classify("echo " + " ".join(["a"] * 70)).level, "blocked")
        self.assertEqual(classify("a\0b").level, "blocked")


class DockerArgvTests(unittest.TestCase):
    def args(self, **kw):
        base = dict(image="python:3.12-slim", argv=["python", "-m", "pytest"], snapshot="/tmp/axion-sbx-abc", limits=ResourceLimits(),
                    network="none", name="axion-1", uid=1000, gid=1000)
        base.update(kw); return docker_argv(**base)

    def test_isolation_flags_present_and_command_last(self):
        a = self.args()
        for flag in ("--rm", "--read-only", "--cap-drop", "no-new-privileges", "--pids-limit", "--memory", "--cpus", "--init"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--network") + 1], "none"); self.assertEqual(a[a.index("--cap-drop") + 1], "ALL")
        self.assertEqual(a[a.index("--user") + 1], "1000:1000"); self.assertEqual(a[a.index("--memory") + 1], a[a.index("--memory-swap") + 1])
        self.assertEqual(a[a.index("python:3.12-slim") + 1:], ["python", "-m", "pytest"])
        self.assertNotIn("--privileged", a); self.assertFalse(any("docker.sock" in x for x in a))

    def test_only_snapshot_is_mounted(self):
        a = self.args(); mounts = [a[i + 1] for i, x in enumerate(a) if x in ("--mount", "-v")]
        self.assertEqual(mounts, ["type=bind,src=/tmp/axion-sbx-abc,dst=/workspace"])

    def test_rejects_injection_and_root(self):
        for kw in ({"snapshot": "/tmp/a,dst=/etc"}, {"snapshot": "/tmp/a b"}, {"image": "x --privileged"}, {"name": "a;b"}, {"network": "host --x"}, {"uid": 0}):
            with self.assertRaises(ValueError, msg=str(kw)): self.args(**kw)

    def test_limits_validated_and_image_mapping(self):
        with self.assertRaises(ValueError): ResourceLimits(memory_mb=1)
        b = DockerBackend({"default": "d", "python": "py", "node": "nd"})
        self.assertEqual([b.image_for(e) for e in ("pytest", "npm", "gcc", "go")], ["py", "nd", "d", "d"])
        with self.assertRaises(ValueError): DockerBackend({})

    def test_docker_missing_is_reported_not_crashing(self):
        b = DockerBackend({"default": "x:1"}, docker_bin="docker-no-existe")
        with mock.patch("os.getuid", return_value=1000), mock.patch("os.getgid", return_value=1000):
            with self.assertRaises(SandboxUnavailable): b.run(["ls"], "/tmp", ResourceLimits(), False)

    def test_refuses_unverified_egress_by_default(self):
        b = DockerBackend({"default": "x:1"})
        with mock.patch("os.getuid", return_value=1000), mock.patch("os.getgid", return_value=1000):
            with self.assertRaises(SandboxUnavailable):
                b.run(["pip", "install", "x"], "/tmp", ResourceLimits(), True)

    def test_refuses_to_run_as_root(self):
        b = DockerBackend({"default": "x:1"})
        with mock.patch("os.getuid", return_value=0):
            with self.assertRaises(ValueError): b.run(["ls"], "/tmp", ResourceLimits(), False)

    def test_local_backend_refused_without_explicit_flag(self):
        import os
        os.environ.pop("AXION_ALLOW_UNSAFE_LOCAL_SANDBOX", None)
        with self.assertRaises(SandboxUnavailable): LocalBackend()

    def test_local_backend_fails_closed_without_network_namespace(self):
        import os
        with mock.patch.dict(os.environ, {"AXION_ALLOW_UNSAFE_LOCAL_SANDBOX": "1"}, clear=False), \
             mock.patch("sandbox.backends.LocalBackend._probe_unshare", return_value=False):
            os.environ.pop("AXION_ALLOW_UNSAFE_LOCAL_NETWORK", None)
            backend = LocalBackend()
            with self.assertRaises(SandboxUnavailable):
                backend.run(["echo", "unsafe"], "/tmp", ResourceLimits(), False)

    def test_local_backend_fails_closed_for_approved_egress_without_explicit_dev_opt_in(self):
        import os
        with mock.patch.dict(os.environ, {"AXION_ALLOW_UNSAFE_LOCAL_SANDBOX": "1"}, clear=False), \
             mock.patch("sandbox.backends.LocalBackend._probe_unshare", return_value=True):
            os.environ.pop("AXION_ALLOW_UNSAFE_LOCAL_NETWORK", None)
            backend = LocalBackend()
            with self.assertRaises(SandboxUnavailable):
                backend.run(["pip", "install", "example"], "/tmp", ResourceLimits(), True)


if __name__ == "__main__":
    unittest.main()
