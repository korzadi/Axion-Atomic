from pathlib import Path
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

if __name__ == "__main__":
    unittest.main()
