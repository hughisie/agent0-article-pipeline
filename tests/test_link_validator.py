import unittest
from unittest.mock import patch

from link_validator import validate_and_fix_links_in_content


class TestLinkValidator(unittest.TestCase):
    def test_link_validator_unlinks_broken_anchor(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n"
            "<p>For full sector statistics, visit the "
            "<a href=\"https://broken.example.com\">official IMET data portal</a>.</p>\n"
            "<!-- /wp:paragraph -->\n"
        )
        with patch("link_validator._check_url", return_value=False), patch(
            "link_validator._repair_link", return_value=None
        ):
            updated, report = validate_and_fix_links_in_content(content, search_enabled=False)
        self.assertIn("official IMET data portal", updated)
        self.assertNotIn("<a href=", updated)
        self.assertEqual(report["unlinked_links"], 1)

    def test_link_validator_replaces_href_when_repair_returns_url(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n"
            "<p>For full sector statistics, visit the "
            "<a href=\"https://broken.example.com\">official IMET data portal</a>.</p>\n"
            "<!-- /wp:paragraph -->\n"
        )
        with patch("link_validator._check_url", return_value=False), patch(
            "link_validator._repair_link", return_value="https://fixed.example.com"
        ):
            updated, report = validate_and_fix_links_in_content(content, search_enabled=False)
        self.assertIn("https://fixed.example.com", updated)
        self.assertIn("official IMET data portal", updated)
        self.assertEqual(report["replaced_links"], 1)


if __name__ == "__main__":
    unittest.main()
