"""Import-level checks for the application scaffold."""

import unittest

from tross_linkedin_api.main import app


class ScaffoldTestCase(unittest.TestCase):
    """Verify the route-free ASGI entry point can be imported."""

    def test_application_metadata(self) -> None:
        """The application factory exposes the expected service title."""
        self.assertEqual(app.title, "Tross LinkedIn Profile API")


if __name__ == "__main__":
    unittest.main()
