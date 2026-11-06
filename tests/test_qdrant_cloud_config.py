"""Verifica que la configuración RAG apunte a Qdrant Cloud, nunca a almacenamiento local."""
import unittest

from pydantic import ValidationError

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

    def test_rejects_insecure_or_local_endpoints(self):
        for endpoint in (
            "http://cluster-example.qdrant.io",
            "http://localhost:6333",
            "https://localhost:6333",
            "https://127.0.0.1:6333",
            "https://qdrant.internal",
            "https://cluster-example.qdrant.io/api",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, qdrant_url=endpoint)

    def test_rejects_url_embedded_credentials_and_query(self):
        for endpoint in (
            "https://user:password@cluster-example.qdrant.io",
            "https://cluster-example.qdrant.io?api_key=unsafe",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, qdrant_url=endpoint)


if __name__ == "__main__":
    unittest.main()
