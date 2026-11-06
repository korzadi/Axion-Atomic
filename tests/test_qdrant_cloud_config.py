"""Verifica que la configuración RAG apunte a Qdrant Cloud, nunca a almacenamiento local."""
import unittest

from api.config import Settings


class QdrantCloudConfigurationTests(unittest.TestCase):
    def test_settings_accept_managed_https_cluster_and_api_key(self):
        settings = Settings(
            _env_file=None,
            qdrant_url="https://cluster-example.eu-central.aws.cloud.qdrant.io",
            qdrant_api_key="test-only-placeholder",
        )
        self.assertEqual(
            settings.qdrant_url,
            "https://cluster-example.eu-central.aws.cloud.qdrant.io",
        )
        self.assertEqual(settings.qdrant_api_key, "test-only-placeholder")

    def test_default_endpoint_never_falls_back_to_local_qdrant(self):
        settings = Settings(_env_file=None)
        self.assertTrue(settings.qdrant_url.startswith("https://"))
        self.assertNotIn("localhost", settings.qdrant_url)
        self.assertNotIn("127.0.0.1", settings.qdrant_url)


if __name__ == "__main__":
    unittest.main()
