"""Secret-safe provider logging tests."""

from __future__ import annotations

import io
import logging
import unittest

import httpx

from tross_linkedin_api.linkedin.transport import (
    LinkedInTransport,
    build_identity_request,
)
from tross_linkedin_api.logging import (
    REDACTED,
    SensitiveDataFilter,
    redact_data,
)


class RedactionTests(unittest.IsolatedAsyncioTestCase):
    def test_recursive_and_inline_secret_redaction(self) -> None:
        raw_secret = "super-secret-value"
        value = {
            "x-api-key": raw_secret,
            "api_key_hashes": raw_secret,
            "api_key_hmac_secret": raw_secret,
            "cookie": f"li_at={raw_secret}; JSESSIONID={raw_secret}",
            "url": f"redis://:{raw_secret}@redis.internal:6379/0",
            "message": (
                f"csrf-token: {raw_secret}; authorization: Bearer {raw_secret}; "
                f"api_key_hmac_secret={raw_secret}"
            ),
        }
        redacted = repr(redact_data(value))
        self.assertNotIn(raw_secret, redacted)
        self.assertIn(REDACTED, redacted)

    async def test_provider_log_contains_hash_not_url_or_secrets(self) -> None:
        raw_secret = "provider-secret-value"

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": {}, "included": [], "meta": {}},
                headers={
                    "content-type": "application/vnd.linkedin.normalized+json+2.1"
                },
            )

        logger = logging.getLogger("tross_linkedin_api.linkedin.transport")
        stream = io.StringIO()
        output = logging.StreamHandler(stream)
        output.setFormatter(
            logging.Formatter("%(message)s %(query_name)s %(profile_id_hash)s")
        )
        output.addFilter(SensitiveDataFilter())
        logger.addHandler(output)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            async with httpx.AsyncClient(
                base_url="https://www.linkedin.com",
                transport=httpx.MockTransport(handler),
                headers={"csrf-token": raw_secret},
            ) as client:
                transport = LinkedInTransport(client)
                await transport.send(
                    build_identity_request("example-person"),
                    profile_id="example-person",
                )
        finally:
            logger.removeHandler(output)
            logger.propagate = True
        log_text = stream.getvalue()
        self.assertIn("linkedin_request", log_text)
        self.assertNotIn(raw_secret, log_text)
        self.assertNotIn("example-person", log_text)
        self.assertNotIn("vanityName", log_text)


if __name__ == "__main__":
    unittest.main()
