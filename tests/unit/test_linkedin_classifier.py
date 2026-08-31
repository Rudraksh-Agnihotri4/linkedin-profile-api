"""Upstream response-classification tests."""

from __future__ import annotations

import unittest

import httpx

from tross_linkedin_api.linkedin.classifier import UpstreamKind, classify_response


def response(
    status_code: int,
    *,
    content_type: str,
    content: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    merged_headers = {"content-type": content_type, **(headers or {})}
    return httpx.Response(
        status_code,
        headers=merged_headers,
        content=content,
        request=httpx.Request("GET", "https://www.linkedin.com/voyager/api/graphql"),
    )


class ClassifierTests(unittest.TestCase):
    normalized = '{"data":{},"included":[],"meta":{}}'

    def test_normalized_json_is_success(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="application/vnd.linkedin.normalized+json+2.1",
                content=self.normalized,
            )
        )
        self.assertEqual(result.kind, UpstreamKind.SUCCESS_JSON)
        self.assertEqual(result.payload, {"data": {}, "included": [], "meta": {}})

    def test_plain_application_json_is_accepted_if_normalized(self) -> None:
        result = classify_response(
            response(200, content_type="application/json", content=self.normalized)
        )
        self.assertEqual(result.kind, UpstreamKind.SUCCESS_JSON)

    def test_profile_content_is_not_mistaken_for_a_control_signal(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="application/vnd.linkedin.normalized+json+2.1",
                content=(
                    '{"data":{},"included":[{"message":'
                    '"Rate limiting specialist","status":"logged out of office"}]}'
                ),
            )
        )
        self.assertEqual(result.kind, UpstreamKind.SUCCESS_JSON)

    def test_login_html_requires_auth(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="text/html",
                content="<title>Sign in | LinkedIn</title>",
            )
        )
        self.assertEqual(result.kind, UpstreamKind.AUTH_REQUIRED)

    def test_challenge_html_stops(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="text/html",
                content="<form action='/checkpoint/challenge/verify'>captcha</form>",
            )
        )
        self.assertEqual(result.kind, UpstreamKind.CHALLENGE)

    def test_html_is_detected_even_with_wrong_content_type(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="text/plain",
                content="<html><title>Sign in | LinkedIn</title></html>",
            )
        )
        self.assertEqual(result.kind, UpstreamKind.AUTH_REQUIRED)

    def test_bom_prefixed_html_and_plain_text_control_signals_stop(self) -> None:
        challenge = classify_response(
            response(
                200,
                content_type="text/plain",
                content="\ufeff<html><form action='/checkpoint'>verify</form></html>",
            )
        )
        auth = classify_response(
            response(
                200,
                content_type="text/plain",
                content="authentication_required",
            )
        )
        self.assertEqual(challenge.kind, UpstreamKind.CHALLENGE)
        self.assertEqual(auth.kind, UpstreamKind.AUTH_REQUIRED)

    def test_normalized_json_auth_signal_stops(self) -> None:
        result = classify_response(
            response(
                200,
                content_type="application/vnd.linkedin.normalized+json+2.1",
                content=(
                    '{"data":{},"included":[],"errors":'
                    '[{"message":"AUTHENTICATION_REQUIRED"}]}'
                ),
            )
        )
        self.assertEqual(result.kind, UpstreamKind.AUTH_REQUIRED)

    def test_auth_status_stops(self) -> None:
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                result = classify_response(
                    response(status_code, content_type="application/json")
                )
                self.assertEqual(result.kind, UpstreamKind.AUTH_REQUIRED)

    def test_throttle_stops_and_parses_retry_after(self) -> None:
        result = classify_response(
            response(
                429,
                content_type="application/json",
                headers={"retry-after": "17"},
            )
        )
        self.assertEqual(result.kind, UpstreamKind.RATE_LIMITED)
        self.assertEqual(result.retry_after_seconds, 17)

    def test_redirect_stops_without_following(self) -> None:
        result = classify_response(
            response(
                302,
                content_type="text/html",
                headers={"location": "https://www.linkedin.com/login"},
            )
        )
        self.assertEqual(result.kind, UpstreamKind.AUTH_REQUIRED)

    def test_malformed_json_is_not_parsed(self) -> None:
        result = classify_response(
            response(200, content_type="application/json", content="not-json")
        )
        self.assertEqual(result.kind, UpstreamKind.MALFORMED_PAYLOAD)

    def test_unknown_html_is_malformed_not_success(self) -> None:
        result = classify_response(
            response(200, content_type="text/html", content="<html>unknown</html>")
        )
        self.assertEqual(result.kind, UpstreamKind.MALFORMED_PAYLOAD)

    def test_transient_and_permanent_statuses_remain_distinct_for_later_retry(self) -> None:
        transient = classify_response(response(503, content_type="application/json"))
        permanent = classify_response(response(404, content_type="application/json"))
        self.assertEqual(transient.kind, UpstreamKind.TRANSIENT_FAILURE)
        self.assertTrue(transient.safe_to_retry)
        self.assertEqual(permanent.kind, UpstreamKind.PERMANENT_FAILURE)
        self.assertFalse(permanent.safe_to_retry)


if __name__ == "__main__":
    unittest.main()
