import unittest
from unittest.mock import patch
from fastapi import HTTPException

from api.security import require_api_key
from api.config import settings


class ApiKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_weak_configured_key_fails_closed(self):
        for key in (None, "short"):
            with patch.object(settings, "api_key", key):
                with self.assertRaises(HTTPException) as raised:
                    await require_api_key(authorization=None, x_api_key=None)
                self.assertEqual(raised.exception.status_code, 503)

    async def test_legacy_api_is_disabled_by_default_even_with_valid_key(self):
        with patch.object(settings, "legacy_api_enabled", False), patch.object(settings, "api_key", "x" * 40):
            with self.assertRaises(HTTPException) as raised:
                await require_api_key(authorization=None, x_api_key="x" * 40)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Legacy API is disabled")

    async def test_legacy_api_requires_explicit_enablement_and_valid_key(self):
        secret = "x" * 40
        with patch.object(settings, "legacy_api_enabled", True), patch.object(settings, "api_key", secret):
            await require_api_key(authorization=None, x_api_key=secret)
            with self.assertRaises(HTTPException) as raised:
                await require_api_key(authorization=None, x_api_key="wrong")
        self.assertEqual(raised.exception.status_code, 401)

    async def test_valid_key_requires_constant_time_comparison(self):
        secret = "x" * 40
        with patch.object(settings, "api_key", secret):
            await require_api_key(authorization=None, x_api_key=secret)
            with self.assertRaises(HTTPException) as raised:
                await require_api_key(authorization=None, x_api_key="wrong")
            self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
