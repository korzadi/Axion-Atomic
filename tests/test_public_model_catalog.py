import unittest

from pydantic import ValidationError

from api.schemas import ChatRequest


class PublicModelCatalogTests(unittest.TestCase):
    def test_default_model_is_the_public_atomic_code_id(self):
        request = ChatRequest(
            project_id="project-1",
            messages=[{"role": "user", "content": "Hola"}],
        )
        self.assertEqual(request.model, "atomic-code")

    def test_only_catalogued_public_model_is_accepted(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                model="qwen-engineering",
                project_id="project-1",
                messages=[{"role": "user", "content": "Hola"}],
            )

    def test_runtime_tag_is_not_a_public_model_identifier(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                model="atomic-code:16k-8k",
                project_id="project-1",
                messages=[{"role": "user", "content": "Hola"}],
            )


if __name__ == "__main__":
    unittest.main()
