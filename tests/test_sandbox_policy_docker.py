import unittest
from unittest import mock

from sandbox.backends import DockerBackend, LocalBackend, ResourceLimits, SandboxUnavailable, _snapshot_tar, docker_argv
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
        base = dict(image="registry.example/python@sha256:" + "a" * 64, argv=["python", "-m", "pytest"], snapshot="/tmp/axion-sbx-abc", limits=ResourceLimits(),
                    network="none", name="axion-1", uid=1000, gid=1000)
        base.update(kw); return docker_argv(**base)

    def test_isolation_flags_present_and_command_last(self):
        a = self.args()
        for flag in ("--rm", "--read-only", "--cap-drop", "no-new-privileges", "--pids-limit", "--memory", "--cpus", "--init"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--network") + 1], "none"); self.assertEqual(a[a.index("--cap-drop") + 1], "ALL")
        self.assertEqual(a[a.index("--user") + 1], "1000:1000"); self.assertEqual(a[a.index("--memory") + 1], a[a.index("--memory-swap") + 1])
        self.assertEqual(a[-3:], ["python", "-m", "pytest"])
        self.assertEqual(a[a.index("registry.example/python@sha256:" + "a" * 64) + 1:a.index("registry.example/python@sha256:" + "a" * 64) + 4],
                         ["sh", "-c", a[a.index("registry.example/python@sha256:" + "a" * 64) + 3]])
        self.assertIn("-i", a)
        self.assertNotIn("--privileged", a); self.assertFalse(any("docker.sock" in x for x in a))

    def test_snapshot_is_streamed_without_bind_mount(self):
        a = self.args()
        self.assertNotIn("--mount", a)
        self.assertNotIn("-v", a)
        workspaces = [a[i + 1] for i, x in enumerate(a) if x == "--tmpfs" and a[i + 1].startswith("/workspace:")]
        self.assertEqual(len(workspaces), 1)
        self.assertIn("uid=1000", workspaces[0])
        self.assertIn("gid=1000", workspaces[0])
        self.assertIn("mode=0700", workspaces[0])
        self.assertIn("size=256m", workspaces[0])

    def test_docker_argv_rejects_mutable_image_tags(self):
        for image in ("python:3.12-slim", "registry.example/image:latest", "registry.example/image"):
            with self.assertRaises(ValueError):
                self.args(image=image)

    def test_rejects_injection_and_root(self):
        for kw in ({"snapshot": "/tmp/a,dst=/etc"}, {"snapshot": "/tmp/a b"}, {"image": "x --privileged"}, {"name": "a;b"}, {"network": "host --x"}, {"uid": 0}):
            with self.assertRaises(ValueError, msg=str(kw)): self.args(**kw)

    def test_limits_validated_and_image_mapping(self):
        with self.assertRaises(ValueError): ResourceLimits(memory_mb=1)
        b = DockerBackend({"default": "registry.example/default@sha256:" + "a" * 64, "python": "registry.example/python@sha256:" + "b" * 64, "node": "registry.example/node@sha256:" + "c" * 64})
        self.assertEqual([b.image_for(e) for e in ("pytest", "npm", "gcc", "go")], ["registry.example/python@sha256:" + "b" * 64, "registry.example/node@sha256:" + "c" * 64, "registry.example/default@sha256:" + "a" * 64, "registry.example/default@sha256:" + "a" * 64])
        with self.assertRaises(ValueError): DockerBackend({})

    def test_backend_rejects_mutable_image_tags(self):
        with self.assertRaisesRegex(ValueError, "digest SHA-256"):
            DockerBackend({"default": "python:3.12-slim"})
        with self.assertRaisesRegex(ValueError, "digest SHA-256"):
            DockerBackend({"default": "registry.example/image:latest"})

    def test_snapshot_tar_includes_regular_files_and_skips_symlinks(self):
        import io
        import os
        import tarfile
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "src"))
            with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
                fh.write("print('ok')\n")
            os.symlink("src/a.py", os.path.join(root, "link.py"))
            archive = io.BytesIO()
            _snapshot_tar(root, archive)
            archive.seek(0)
            with tarfile.open(fileobj=archive, mode="r") as tar:
                names = tar.getnames()
                contents = tar.extractfile("src/a.py").read()

        self.assertEqual(names, ["src/a.py"])
        self.assertEqual(contents, b"print('ok')\n")

    def test_backend_streams_tar_and_cleans_container(self):
        from sandbox.runner import ExecResult
        import io
        import os
        import tarfile
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "a.txt"), "w", encoding="utf-8") as fh:
                fh.write("hola")
            captured = {}

            def fake_run(cmd, cwd, env, timeout, max_bytes, **kwargs):
                captured["cmd"] = cmd
                captured["env"] = env
                captured["stdin"] = kwargs["stdin"].read()
                return ExecResult(0, "", "", False, False, 0.1, "docker")

            b = DockerBackend(
                {"default": "registry.example/x@sha256:" + "a" * 64},
                docker_host="tcp://sandbox:2376",
                docker_tls_verify=True,
                docker_cert_path="/run/secrets/docker-ca",
            )
            with mock.patch("os.getuid", return_value=1000), mock.patch("os.getgid", return_value=1000), \
                 mock.patch("sandbox.backends.run_bounded", side_effect=fake_run), \
                 mock.patch("sandbox.backends.subprocess.run") as cleanup:
                result = b.run(["python", "-m", "pytest"], root, ResourceLimits(), False)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(captured["cmd"][-3:], ["python", "-m", "pytest"])
        self.assertNotIn("--mount", captured["cmd"])
        self.assertIn("--pull=never", captured["cmd"])
        self.assertEqual(captured["env"]["DOCKER_TLS_VERIFY"], "1")
        self.assertEqual(captured["env"]["DOCKER_CERT_PATH"], "/run/secrets/docker-ca")
        with tarfile.open(fileobj=io.BytesIO(captured["stdin"]), mode="r") as tar:
            self.assertEqual(tar.extractfile("a.txt").read(), b"hola")
        cleanup.assert_called_once()
        self.assertIn("-f", cleanup.call_args.args[0])

    def test_docker_missing_is_reported_not_crashing(self):
        b = DockerBackend({"default": "registry.example/x@sha256:" + "a" * 64}, docker_bin="docker-no-existe")
        with mock.patch("os.getuid", return_value=1000), mock.patch("os.getgid", return_value=1000):
            with self.assertRaises(SandboxUnavailable): b.run(["ls"], "/tmp", ResourceLimits(), False)

    def test_refuses_unverified_egress_by_default(self):
        b = DockerBackend({"default": "registry.example/x@sha256:" + "a" * 64})
        with mock.patch("os.getuid", return_value=1000), mock.patch("os.getgid", return_value=1000):
            with self.assertRaises(SandboxUnavailable):
                b.run(["pip", "install", "x"], "/tmp", ResourceLimits(), True)

    def test_rejects_configuration_that_attempts_to_enable_unverified_egress(self):
        with self.assertRaises(SandboxUnavailable):
            DockerBackend({"default": "registry.example/x@sha256:" + "a" * 64}, allow_egress=True)
        with self.assertRaises(SandboxUnavailable):
            DockerBackend({"default": "registry.example/x@sha256:" + "a" * 64}, egress_network="axion-sandbox-egress")

    def test_refuses_to_run_as_root(self):
        b = DockerBackend({"default": "registry.example/x@sha256:" + "a" * 64})
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
