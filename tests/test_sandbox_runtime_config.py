import unittest
from types import SimpleNamespace

from api.sandbox_runtime import configured_sandbox_backend
from sandbox.backends import DockerBackend, SandboxUnavailable

IMAGE = "registry.example/sandbox@sha256:" + "a" * 64


def settings(**changes):
    base = dict(
        sandbox_docker_enabled=True,
        sandbox_docker_host="tcp://sandbox-daemon:2376",
        sandbox_docker_bin="docker",
        sandbox_docker_images={"default": IMAGE},
        sandbox_docker_tls_verify=True,
        sandbox_docker_cert_path="/run/secrets/docker-ca",
    )
    base.update(changes)
    return SimpleNamespace(**base)


class SandboxRuntimeConfigTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertIsNone(configured_sandbox_backend(settings(sandbox_docker_enabled=False)))

    def test_requires_explicit_remote_daemon(self):
        for host in (None, "", "unix:///var/run/docker.sock", "/var/run/docker.sock", "http://sandbox:2375"):
            with self.subTest(host=host):
                with self.assertRaises(SandboxUnavailable):
                    configured_sandbox_backend(settings(sandbox_docker_host=host))

    def test_rejects_unpinned_images_and_missing_default(self):
        with self.assertRaises(SandboxUnavailable):
            configured_sandbox_backend(settings(sandbox_docker_images={}))
        with self.assertRaises(SandboxUnavailable):
            configured_sandbox_backend(settings(sandbox_docker_images={"default": "python:3.12-slim"}))

    def test_tcp_requires_tls_and_certificate(self):
        with self.assertRaises(SandboxUnavailable):
            configured_sandbox_backend(settings(sandbox_docker_tls_verify=False))
        with self.assertRaises(SandboxUnavailable):
            configured_sandbox_backend(settings(sandbox_docker_cert_path=""))

    def test_ssh_daemon_is_allowed_without_local_socket(self):
        backend = configured_sandbox_backend(settings(
            sandbox_docker_host="ssh://sandbox@daemon.example",
            sandbox_docker_tls_verify=False,
            sandbox_docker_cert_path=None,
        ))
        self.assertEqual(backend.docker_host, "ssh://sandbox@daemon.example")

    def test_rejects_invalid_binary(self):
        with self.assertRaises(SandboxUnavailable):
            configured_sandbox_backend(settings(sandbox_docker_bin="docker; rm -rf /"))

    def test_builds_backend_with_remote_host(self):
        backend = configured_sandbox_backend(settings())
        self.assertIsInstance(backend, DockerBackend)
        self.assertEqual(backend.docker_host, "tcp://sandbox-daemon:2376")
        self.assertEqual(backend.docker_bin, "docker")
        self.assertTrue(backend.docker_tls_verify)
        self.assertEqual(backend.docker_cert_path, "/run/secrets/docker-ca")
        self.assertEqual(backend.image_for("unknown"), IMAGE)


if __name__ == "__main__":
    unittest.main()
