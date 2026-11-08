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

    def test_new_env_database_url_uses_configured_postgres_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "install_vps.sh").write_text(self.script, encoding="utf-8")
            (root / "compose.yaml").write_text("services: {}", encoding="utf-8")
            (root / ".env.example").write_text(
                "POSTGRES_DB=atomic_custom\n"
                "POSTGRES_USER=atomic_user\n"
                "POSTGRES_PASSWORD=CHANGE_THIS\n"
                "DATABASE_URL=postgresql+psycopg://old:old@postgres:5432/old\n"
                "API_KEY=REPLACE_ME\n",
                encoding="utf-8",
            )
            for name in ("workspace", "knowledge", "backups"):
                (root / name).mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text(
                "#!/usr/bin/env sh\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = version ]; then exit 0; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                ["bash", str(scripts / "install_vps.sh"), "--prepare"],
                cwd=root, env=env, text=True, capture_output=True,
                check=False, timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = dict(
                line.split("=", 1)
                for line in (root / ".env").read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.startswith("#")
            )
            self.assertTrue(values["DATABASE_URL"].startswith(
                "postgresql+psycopg://atomic_user:"
            ))
            self.assertTrue(values["DATABASE_URL"].endswith(
                "@postgres:5432/atomic_custom"
            ))
            self.assertNotIn("CHANGE_THIS", values["DATABASE_URL"])
            self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)

    def test_backup_is_created_before_database_migrations(self):
        self.assertLess(self.script.index("pg_dump"), self.script.index("python -m api.migrate"))
        self.assertIn("pre-migration-", self.script)

    def test_existing_project_and_persistent_volume_block_deploy(self):
        for token in ("volume=$volume", "for volume in axion_atomic_pgdata axyron_atomic_pgdata", "project=axion-atomic", "8070", "5433"):
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
        self.assertIn('docker volume inspect "$volume"', self.script)
        self.assertIn('for volume in axion_atomic_pgdata axyron_atomic_pgdata', self.script)
        self.assertIn('"$VOLUME_EXISTS" == 1', self.script)

    def test_read_only_vps_inventory_is_present_and_scoped(self):
        inventory = (ROOT / "scripts/inspect_vps_state.sh").read_text(encoding="utf-8")
        for token in (
            "axion-atomic",
            "axyron-atomic",
            "axion_atomic_pgdata",
            "axyron_atomic_pgdata",
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
        self.assertIn("axyron_atomic_pgdata", self.doc)
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


    def test_prepare_rejects_dangling_env_symlink_before_creating_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "install_vps.sh").write_text(self.script, encoding="utf-8")
            (root / "compose.yaml").write_text("services: {}", encoding="utf-8")
            (root / ".env.example").write_text("API_KEY=placeholder", encoding="utf-8")
            for name in ("workspace", "knowledge", "backups"):
                (root / name).mkdir()
            target = root / "missing-target"
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
            self.assertTrue((root / ".env").is_symlink())
            self.assertFalse(target.exists())


    def test_prepare_preserves_existing_regular_env_and_sets_private_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "install_vps.sh").write_text(self.script, encoding="utf-8")
            (root / "compose.yaml").write_text("services: {}", encoding="utf-8")
            (root / ".env.example").write_text("API_KEY=placeholder", encoding="utf-8")
            for name in ("workspace", "knowledge", "backups"):
                (root / name).mkdir()
            env_file = root / ".env"
            env_file.write_text("API_KEY=keep-this-value", encoding="utf-8")
            env_file.chmod(0o644)
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
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(env_file.read_text(encoding="utf-8"), "API_KEY=keep-this-value")
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_frontend_upgrade_validates_split_stack_port_ownership(self):
        upgrade = self.script.split("upgrade_frontend(){", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('FRONTEND="$(${C[@]} ps -q frontend)"', upgrade)
        self.assertIn('docker port "$FRONTEND"', upgrade)
        self.assertIn('API_EXPOSED=', upgrade)
        self.assertIn('8000/tcp', upgrade)
        self.assertNotIn('docker port "$API"', upgrade)
        self.assertIn('frontend existente no está ejecutándose', upgrade)

if __name__ == "__main__":
    unittest.main()


class PostgresRestoreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = ROOT / "scripts/restore_postgres.sh"

    def _fake_docker(self, root, project="disposable"):
        fake_bin = root / "bin"
        fake_bin.mkdir(exist_ok=True)
        docker = fake_bin / "docker"
        docker.write_text(
            """#!/usr/bin/env bash
if [[ "$1" == "inspect" ]]; then
  if [[ "$*" == *"State.Running"* ]]; then echo true; exit 0; fi
  if [[ "$*" == *"com.docker.compose.project"* ]]; then echo "${FAKE_PROJECT:-disposable}"; exit 0; fi
  exit 1
fi
if [[ "$1" == "exec" ]]; then
  if [[ "$*" == *"pg_restore --list"* ]]; then cat >/dev/null; exit 0; fi
  if [[ "$*" == *"pg_restore --no-owner"* ]]; then cat >/dev/null; exit 0; fi
  if [[ "$*" == *"psql"* ]]; then
    count=0
    [[ -f "${FAKE_STATE}" ]] && count="$(cat "${FAKE_STATE}")"
    count=$((count + 1))
    printf '%s' "$count" > "${FAKE_STATE}"
    if [[ "$count" -eq 1 ]]; then echo 0; else echo 3; fi
    exit 0
  fi
fi
exit 1
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_STATE"] = str(root / "state")
        env["FAKE_PROJECT"] = project
        return env

    def _run(self, root, env, database="restore_probe", confirm="RESTORE restore_probe", backup=None):
        backup = backup or (root / "backup.dump")
        if not backup.exists():
            backup.write_bytes(b"not-a-real-dump")
        completed = subprocess.run(
            ["bash", str(self.script), "--container", "pg-disposable",
             "--database", database, "--user", "restore_user",
             "--backup", str(backup), "--confirm", confirm],
            cwd=root, env=env, text=True, capture_output=True, check=False, timeout=10,
        )
        return completed

    def test_script_exists_and_does_not_target_production_stack(self):
        text = self.script.read_text(encoding="utf-8")
        for token in ("pg_restore --list", "pg_restore --no-owner", "--exit-on-error",
                      "axyron-atomic", "axion-atomic", "RESTORE $DATABASE"):
            self.assertIn(token, text)

    def test_refuses_production_database_names_before_docker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self._fake_docker(root)
            for name in ("axion_atomic", "axyron_atomic", "postgres", "template1"):
                completed = self._run(root, env, database=name, confirm=f"RESTORE {name}")
                self.assertNotEqual(completed.returncode, 0, name)
                self.assertIn("producción o del sistema", completed.stderr)

    def test_refuses_backup_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self._fake_docker(root)
            target = root / "target.dump"
            target.write_bytes(b"data")
            link = root / "link.dump"
            link.symlink_to(target)
            completed = self._run(root, env, backup=link)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("enlace simbólico", completed.stderr)

    def test_refuses_production_compose_container(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self._fake_docker(root, project="axyron-atomic")
            completed = self._run(root, env)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("stack de producción", completed.stderr)

    def test_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self._fake_docker(root)
            completed = self._run(root, env, confirm="RESTORE otra_base")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Confirmación incorrecta", completed.stderr)

    def test_restores_into_empty_disposable_database_and_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self._fake_docker(root)
            completed = self._run(root, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Restauración verificada", completed.stdout)
