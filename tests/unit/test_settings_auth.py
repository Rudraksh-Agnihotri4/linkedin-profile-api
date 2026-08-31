"""Settings, session-shape, and digest-authentication tests."""

from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from tross_linkedin_api.auth.api_key import require_api_key
from tross_linkedin_api.errors import ApiKeyInvalidError
from tross_linkedin_api.settings import Settings


API_KEY = "test-evaluator-key"
SHA256_DIGEST = hashlib.sha256(API_KEY.encode()).hexdigest()


def settings_kwargs() -> dict[str, object]:
    return {
        "app_env": "test",
        "public_base_url": "https://api.example.test",
        "api_key_hashes": frozenset({SHA256_DIGEST}),
        "linkedin_user_agent": "tross-test-client/1.0",
        "linkedin_li_at": "test-li-at-secret",
        "linkedin_jsessionid": '"ajax:test-session-secret"',
        "linkedin_csrf_token": "ajax:test-session-secret",
    }


class SettingsAndAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sha256_and_hmac_digest_modes(self) -> None:
        sha_settings = Settings(**settings_kwargs())
        self.assertEqual(await require_api_key(API_KEY, sha_settings), SHA256_DIGEST[:12])

        hmac_secret = "test-hmac-secret"
        hmac_digest = hmac.new(
            hmac_secret.encode(), API_KEY.encode(), hashlib.sha256
        ).hexdigest()
        hmac_kwargs = settings_kwargs()
        hmac_kwargs.update(
            api_key_hashes=frozenset({hmac_digest}),
            api_key_hmac_secret=hmac_secret,
        )
        hmac_settings = Settings(**hmac_kwargs)
        self.assertEqual(
            await require_api_key(API_KEY, hmac_settings), hmac_digest[:12]
        )
        with self.assertRaises(ApiKeyInvalidError):
            await require_api_key("wrong-key", hmac_settings)

    async def test_hmac_mode_does_not_fall_back_to_plain_sha256(self) -> None:
        kwargs = settings_kwargs()
        kwargs["api_key_hmac_secret"] = "test-hmac-secret"
        with self.assertRaises(ApiKeyInvalidError):
            await require_api_key(API_KEY, Settings(**kwargs))

    def test_jsessionid_is_normalized_and_must_match_csrf(self) -> None:
        quoted = Settings(**settings_kwargs())
        self.assertEqual(
            quoted.linkedin_jsessionid_cookie_value,
            '"ajax:test-session-secret"',
        )

        unquoted_kwargs = settings_kwargs()
        unquoted_kwargs["linkedin_jsessionid"] = "ajax:test-session-secret"
        unquoted = Settings(**unquoted_kwargs)
        self.assertEqual(
            unquoted.linkedin_jsessionid_cookie_value,
            '"ajax:test-session-secret"',
        )

        for invalid_value in ('"ajax:test-session-secret', "not-ajax"):
            with self.subTest(invalid_value=invalid_value):
                invalid_kwargs = settings_kwargs()
                invalid_kwargs["linkedin_jsessionid"] = invalid_value
                with self.assertRaises(ValueError):
                    Settings(**invalid_kwargs)

        mismatch_kwargs = settings_kwargs()
        mismatch_kwargs["linkedin_csrf_token"] = "ajax:different"
        with self.assertRaises(ValueError):
            Settings(**mismatch_kwargs)

    def test_production_requires_https_and_non_finite_timeouts_fail(self) -> None:
        production_kwargs = settings_kwargs()
        production_kwargs.update(
            app_env="production",
            public_base_url="http://api.example.test",
        )
        with self.assertRaises(ValueError):
            Settings(**production_kwargs)

        timeout_kwargs = settings_kwargs()
        timeout_kwargs["upstream_read_timeout_seconds"] = float("nan")
        with self.assertRaises(ValueError):
            Settings(**timeout_kwargs)

    def test_unimplemented_redis_settings_are_not_required_for_startup(self) -> None:
        environment = {
            "APP_ENV": "test",
            "PUBLIC_BASE_URL": "https://api.example.test",
            "API_KEY_HASHES": SHA256_DIGEST,
            "LINKEDIN_USER_AGENT": "tross-test-client/1.0",
            "LINKEDIN_LI_AT": "test-li-at-secret",
            "LINKEDIN_JSESSIONID": '"ajax:test-session-secret"',
            "LINKEDIN_CSRF_TOKEN": "ajax:test-session-secret",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.app_env, "test")
        self.assertFalse(hasattr(settings, "redis_url"))

    def test_secret_fields_are_absent_from_repr(self) -> None:
        kwargs = settings_kwargs()
        kwargs["api_key_hmac_secret"] = "test-hmac-secret"
        rendered = repr(Settings(**kwargs))
        for secret in (
            "test-hmac-secret",
            "test-li-at-secret",
            "test-session-secret",
            SHA256_DIGEST,
        ):
            self.assertNotIn(secret, rendered)


if __name__ == "__main__":
    unittest.main()
