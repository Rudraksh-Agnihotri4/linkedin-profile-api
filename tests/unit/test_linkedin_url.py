"""Strict LinkedIn URL canonicalization tests."""

from __future__ import annotations

import unittest

from tross_linkedin_api.errors import InvalidProfileUrlError
from tross_linkedin_api.url.linkedin_url import (
    MAX_PROFILE_URL_LENGTH,
    canonicalize_linkedin_profile_url,
)


class LinkedInUrlTests(unittest.TestCase):
    def test_valid_urls_are_canonicalized(self) -> None:
        cases = (
            ("https://www.linkedin.com/in/john-smith", "john-smith"),
            ("https://linkedin.com/in/john-smith/", "john-smith"),
            ("http://www.linkedin.com/in/john-smith", "john-smith"),
            ("http://ca.linkedin.com/in/john-smith", "john-smith"),
            ("https://www.linkedin.com/in/JohnSmith", "johnsmith"),
            ("https://www.linkedin.com/in/john-smith?trk=profile", "john-smith"),
            ("https://www.linkedin.com/in/john-smith#about", "john-smith"),
            ("https://www.linkedin.com/in/john-smith/es", "john-smith"),
        )
        for value, expected_profile_id in cases:
            with self.subTest(value=value):
                result = canonicalize_linkedin_profile_url(value)
                self.assertEqual(result.profile_id, expected_profile_id)
                self.assertEqual(
                    result.canonical_public_url,
                    f"https://www.linkedin.com/in/{expected_profile_id}",
                )

    def test_invalid_urls_are_rejected(self) -> None:
        cases = (
            "",
            "x" * (MAX_PROFILE_URL_LENGTH + 1),
            "ftp://www.linkedin.com/in/john-smith",
            "https://evil.com/in/john-smith",
            "https://linkedin.com.evil.com/in/john-smith",
            "https://evil.linkedin.com/in/john-smith",
            "https://www.linkedin.com:443/in/john-smith",
            "https://www.linkedin.com:/in/john-smith",
            "https://user:pass@www.linkedin.com/in/john-smith",
            "https://www.linkedin.com/company/example",
            "https://www.linkedin.com/in/ab",
            "https://www.linkedin.com/in/linkedin",
            "https://www.linkedin.com/in/name_with_underscore",
            "https://www.linkedin.com/in/name%2Fother",
            "https://www.linkedin.com/in/john-smith/EN",
            "https://www.linkedin.com/in//john-smith",
            "https://www.linkedin.com/in/john-smith\n",
            "https://www.linkedin.com/in/john\tsmith",
            "https://www.linkedin.com./in/john-smith",
            "https://ｗｗｗ.linkedin.com/in/john-smith",
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(InvalidProfileUrlError):
                    canonicalize_linkedin_profile_url(value)

    def test_raw_url_is_not_retained(self) -> None:
        raw = "https://www.linkedin.com/in/JohnSmith?secret=not-retained#fragment"
        result = canonicalize_linkedin_profile_url(raw)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("fragment", repr(result))


if __name__ == "__main__":
    unittest.main()
