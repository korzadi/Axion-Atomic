from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class VpsInstallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "scripts/install_vps.sh").read_text(encoding="utf-8")
        cls.doc = (ROOT / "docs/VPS_INSTALLATION.md").read_text(encoding="utf-8")

    def test_staged_modes_and_explicit_deploy_confirmation(self):
        for token in ("--prepare", "--check", "--deploy", "DEPLOY AXYRON ATOMIC"):
            self.assertIn(token, self.script)

    def test_backup_is_created_before_database_migrations(self):
        self.assertLess(self.script.index("pg_dump"), self.script.index("python -m api.migrate"))
        self.assertIn("pre-migration-", self.script)

    def test_existing_project_and_persistent_volume_block_deploy(self):
        for token in ("volume=axion_atomic_pgdata", "project=axion-atomic", "8070", "5433"):
            self.assertIn(token, self.script)

    def test_knowledge_directory_is_readable_but_not_writable_by_api(self):
        self.assertIn('install -d -o 10001 -g 10001 -m 500 "$ROOT/knowledge"', self.script)
        self.assertIn('KNOWLEDGE_META="$(stat -c %u:%a "$ROOT/knowledge")"', self.script)
        self.assertIn('"10001:500"', self.script)

    def test_check_is_read_only_and_requires_explicit_prepare(self):
        check = self.script.split('case "$MODE" in', 1)[1]
        self.assertIn('--check) [[ -f "$ENV_FILE" ]] || die', check)
        self.assertIn('Validación completada sin modificar archivos', check)
        self.assertNotIn('--check) [[ -f "$ENV_FILE" ]] || prepare', self.script)

    def test_existing_named_volume_blocks_even_without_running_container(self):
        self.assertIn('docker volume inspect axion_atomic_pgdata', self.script)
        self.assertIn('"$VOLUME_EXISTS" == 1', self.script)

    def test_read_only_vps_inventory_is_present_and_scoped(self):
        inventory = (ROOT / "scripts/inspect_vps_state.sh").read_text(encoding="utf-8")
        for token in (
            "axion-atomic",
            "axyron-atomic",
            "axion_atomic_pgdata",
            "docker volume inspect",
            "docker ps -a",
            "ss -ltnH",
            "No se mostraron secretos",
        ):
            self.assertIn(token, inventory)
        for forbidden in (
            "docker compose up",
            "docker compose down",
            "docker restart",
            "docker stop",
            "docker rm",
            "docker volume rm",
            "docker volume prune",
            "docker system prune",
            "cat .env",
            "docker inspect .*Config.Env",
        ):
            self.assertNotIn(forbidden, inventory)

    def test_read_only_inventory_runs_with_empty_docker_state(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_bin = Path(temp) / "bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text(
                """#!/usr/bin/env bash
case "$1 $2" in
  'info ') exit 0 ;;
  'ps -a') exit 0 ;;
  'volume inspect') exit 1 ;;
  'network ls') exit 0 ;;
  *) exit 0 ;;
esac
""",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                ["bash", str(ROOT / "scripts/inspect_vps_state.sh")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("REPOSITORIO", completed.stdout)
            self.assertIn("CONTENEDORES DE LOS PROYECTOS AXYRON", completed.stdout)
            self.assertIn("VOLUMEN POSTGRESQL PERSISTENTE", completed.stdout)
            self.assertIn("REDES DE LOS PROYECTOS AXYRON", completed.stdout)
            self.assertIn("Inventario de solo lectura terminado", completed.stdout)

    def test_workspace_permissions_are_checked_before_deploy(self):
        self.assertIn("WORKSPACE_META", self.script)
        self.assertIn("10001:700", self.script)
        self.assertIn("No se cambia automáticamente", self.script)

    def test_auth_legacy_api_and_command_execution_remain_disabled(self):
        for token in ("AUTH_ENABLED", "LEGACY_API_ENABLED", "ENABLE_COMMAND_EXECUTION"):
            self.assertIn(token, self.script)

    def test_no_destructive_or_shared_host_operations(self):
        for token in ("compose down", "volume rm", "volume prune", "system prune", "ufw ", "systemctl ", "nginx -s"):
            self.assertNotIn(token, self.script)

    def test_documentation_warns_about_existing_vps_resources(self):
        self.assertIn("axion_atomic_pgdata", self.doc)
        self.assertIn("No borres ni detengas", self.doc)


    def test_prepare_rejects_env_symlink_without_changing_target_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "install_vps.sh").write_text(self.script, encoding="utf-8")
            (root / "compose.yaml").write_text("services: {}", encoding="utf-8")
            (root / ".env.example").write_text("API_KEY=placeholder", encoding="utf-8")
            for name in ("workspace", "knowledge", "backups"):
                (root / name).mkdir()
            target = root / "sensitive-target"
            target.write_text("do-not-change", encoding="utf-8")
            target.chmod(0o644)
            (root / ".env").symlink_to(target)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text(
                """#!/usr/bin/env sh
if [ "$1" = compose ] && [ "$2" = version ]; then exit 0; fi
exit 0
""",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                ["bash", str(scripts / "install_vps.sh"), "--prepare"],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("archivo regular y no un enlace simbólico", completed.stderr)
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            self.assertEqual(target.read_text(encoding="utf-8"), "do-not-change")

if __name__ == "__main__":
    unittest.main()
