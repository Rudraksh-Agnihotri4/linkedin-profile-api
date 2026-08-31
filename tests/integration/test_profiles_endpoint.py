"""Profile endpoint tests with a fully mocked LinkedIn transport."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from tross_linkedin_api.app import create_app
from tross_linkedin_api.linkedin.transport import (
    CARDS_QUERY_ID,
    COMPONENTS_QUERY_ID,
    IDENTITY_QUERY_ID,
)
from tross_linkedin_api.settings import Settings


FIXTURES = Path(__file__).parents[1] / "fixtures" / "linkedin"
API_KEY = "test-evaluator-key"


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_settings() -> Settings:
    return Settings(
        app_env="test",
        public_base_url="https://api.example.test",
        api_key_hashes=frozenset({hashlib.sha256(API_KEY.encode()).hexdigest()}),
        linkedin_user_agent="tross-test-client/1.0",
        linkedin_li_at="test-li-at-secret",
        linkedin_jsessionid='"ajax:test-session-secret"',
        linkedin_csrf_token="ajax:test-session-secret",
    )


class ProfileEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _request(
        self,
        upstream_handler,
        *,
        body: object | None = None,
        raw_content: bytes | None = None,
        api_key: str | None = API_KEY,
    ) -> tuple[httpx.Response, list[httpx.Request]]:
        captured: list[httpx.Request] = []

        async def capture(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return await upstream_handler(request)

        app = create_app(
            settings=test_settings(),
            upstream_transport=httpx.MockTransport(capture),
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                base_url="https://service.example.test",
                transport=httpx.ASGITransport(
                    app=app,
                    raise_app_exceptions=False,
                ),
            ) as client:
                headers = {"x-api-key": api_key} if api_key is not None else {}
                kwargs: dict[str, object] = {"headers": headers}
                if raw_content is not None:
                    kwargs["content"] = raw_content
                    headers["content-type"] = "application/json"
                else:
                    kwargs["json"] = (
                        body
                        if body is not None
                        else {
                            "profile_url": "https://www.linkedin.com/in/Example-Person?trk=share"
                        }
                    )
                response = await client.post("/v1/profiles:resolve", **kwargs)
        return response, captured

    async def test_happy_path_runs_exact_three_call_flow(self) -> None:
        payloads = {
            IDENTITY_QUERY_ID: fixture("spike0b_identity.json"),
            COMPONENTS_QUERY_ID: fixture("spike0b_components.json"),
            CARDS_QUERY_ID: fixture("spike0b_cards.json"),
        }

        async def upstream(request: httpx.Request) -> httpx.Response:
            query_id = parse_qs(urlsplit(str(request.url)).query)["queryId"][0]
            return httpx.Response(
                200,
                json=payloads[query_id],
                headers={
                    "content-type": "application/vnd.linkedin.normalized+json+2.1"
                },
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(captured), 3)
        query_ids = [
            parse_qs(urlsplit(str(request.url)).query)["queryId"][0]
            for request in captured
        ]
        self.assertEqual(
            query_ids,
            [IDENTITY_QUERY_ID, COMPONENTS_QUERY_ID, CARDS_QUERY_ID],
        )
        variables = [
            parse_qs(urlsplit(str(request.url)).query)["variables"][0]
            for request in captured
        ]
        self.assertEqual(variables[0], "(vanityName:example-person)")
        self.assertIn("sectionType:content-collections", variables[1])
        self.assertIn("sectionType:CONTENT_COLLECTIONS_DETAILS", variables[2])
        data = response.json()
        self.assertEqual(data["profile"]["name"], "Example Person")
        self.assertEqual(data["profile"]["canonical_id"], "example-person")
        self.assertEqual(data["sections"]["identity"]["status"], "complete")
        self.assertEqual(data["sections"]["about"]["status"], "unavailable")
        self.assertEqual(data["sections"]["languages"]["status"], "unavailable")
        self.assertEqual(data["profile"]["experience"], [])
        self.assertEqual(response.headers["x-cache"], "miss")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-request-id"], data["request_id"])
        self.assertEqual(data["cache"]["stored_at"], data["cache"]["expires_at"])
        self.assertEqual(captured[0].headers["csrf-token"], "ajax:test-session-secret")
        self.assertIn("li_at=test-li-at-secret", captured[0].headers["cookie"])
        self.assertIn(
            'JSESSIONID="ajax:test-session-secret"',
            captured[0].headers["cookie"],
        )

    async def test_request_ids_are_fresh_across_resolutions(self) -> None:
        payloads = {
            IDENTITY_QUERY_ID: fixture("spike0b_identity.json"),
            COMPONENTS_QUERY_ID: fixture("spike0b_components.json"),
            CARDS_QUERY_ID: fixture("spike0b_cards.json"),
        }

        async def upstream(request: httpx.Request) -> httpx.Response:
            query_id = parse_qs(urlsplit(str(request.url)).query)["queryId"][0]
            return httpx.Response(
                200,
                json=payloads[query_id],
                headers={
                    "content-type": "application/vnd.linkedin.normalized+json+2.1"
                },
            )

        first, first_calls = await self._request(upstream)
        second, second_calls = await self._request(upstream)
        self.assertEqual(len(first_calls), 3)
        self.assertEqual(len(second_calls), 3)
        self.assertNotEqual(first.json()["request_id"], second.json()["request_id"])

    async def test_invalid_url_is_rejected_before_upstream(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            self.fail("upstream must not be called for an invalid URL")

        response, captured = await self._request(
            upstream,
            body={"profile_url": "https://linkedin.com.evil.test/in/example-person"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_profile_url")
        self.assertEqual(captured, [])

    async def test_missing_and_invalid_api_keys_never_call_upstream(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            self.fail("upstream must not be called for API-key failures")

        missing, missing_calls = await self._request(upstream, api_key=None)
        invalid, invalid_calls = await self._request(upstream, api_key="wrong-key")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["code"], "api_key_missing")
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["code"], "api_key_invalid")
        self.assertEqual(missing_calls, [])
        self.assertEqual(invalid_calls, [])

    async def test_challenge_stops_without_remaining_calls(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text="<html><form action='/checkpoint/challenge/verify'>captcha</form></html>",
                headers={"content-type": "text/html"},
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "linkedin_challenge_required")
        self.assertEqual(len(captured), 1)
        self.assertNotIn("checkpoint", response.text.lower())

    async def test_429_stops_without_retry(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"message": "rate limited"},
                headers={
                    "content-type": "application/json",
                    "retry-after": "999999",
                },
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "linkedin_rate_limited")
        self.assertEqual(response.headers["retry-after"], "3600")
        self.assertEqual(len(captured), 1)

    async def test_429_without_valid_retry_after_uses_bounded_default(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"message": "rate limited"},
                headers={
                    "content-type": "application/json",
                    "retry-after": "not-a-valid-delay",
                },
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["retry_after_seconds"], 60)
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertEqual(len(captured), 1)

    async def test_redirect_is_not_followed(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302,
                headers={
                    "content-type": "text/html",
                    "location": "https://www.linkedin.com/login",
                },
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "linkedin_auth_required")
        self.assertEqual(len(captured), 1)

    async def test_upstream_auth_failure_maps_without_leaking_body(self) -> None:
        upstream_secret = "raw-upstream-secret"

        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                text=f"session invalid: {upstream_secret}",
                headers={"content-type": "text/plain", "retry-after": "10"},
            )

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "linkedin_auth_required")
        self.assertNotIn(upstream_secret, response.text)
        self.assertNotIn("retry-after", response.headers)
        self.assertEqual(len(captured), 1)

    async def test_malformed_json_request_uses_problem_details(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            self.fail("upstream must not be called for malformed JSON")

        response, captured = await self._request(
            upstream,
            raw_content=b'{"profile_url":',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_json")
        self.assertTrue(response.headers["content-type"].startswith("application/problem+json"))
        self.assertEqual(captured, [])

    async def test_unexpected_failure_uses_sanitized_problem_details(self) -> None:
        internal_secret = "internal-exception-secret"

        async def upstream(request: httpx.Request) -> httpx.Response:
            raise RuntimeError(internal_secret)

        response, captured = await self._request(upstream)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "internal_error")
        self.assertNotIn(internal_secret, response.text)
        self.assertEqual(len(captured), 1)

    async def test_lifespan_owns_and_closes_one_http_client(self) -> None:
        async def upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        app = create_app(
            settings=test_settings(),
            upstream_transport=httpx.MockTransport(upstream),
        )
        async with app.router.lifespan_context(app):
            client = app.state.http_client
            self.assertFalse(client.is_closed)
            self.assertIs(app.state.linkedin_client._transport._http_client, client)
        self.assertTrue(client.is_closed)

    def test_openapi_declares_api_key_and_problem_details_media_type(self) -> None:
        app = create_app(
            settings=test_settings(),
            upstream_transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        )
        schema = app.openapi()
        operation = schema["paths"]["/v1/profiles:resolve"]["post"]
        self.assertEqual(operation["security"], [{"APIKeyHeader": []}])
        self.assertEqual(
            schema["components"]["securitySchemes"]["APIKeyHeader"],
            {"type": "apiKey", "in": "header", "name": "x-api-key"},
        )
        self.assertEqual(
            set(operation["responses"]["200"]["headers"]),
            {"x-request-id", "x-cache", "cache-control"},
        )
        for status_code in (
            "400",
            "401",
            "403",
            "404",
            "422",
            "429",
            "500",
            "502",
            "503",
            "504",
        ):
            self.assertEqual(
                set(operation["responses"][status_code]["content"]),
                {"application/problem+json"},
            )
        self.assertIn("retry-after", operation["responses"]["429"]["headers"])
        self.assertIn("retry-after", operation["responses"]["503"]["headers"])


if __name__ == "__main__":
    unittest.main()
