import unittest

from blocks_utils import finalise_source_credits


class TestSourceCredits(unittest.TestCase):
    def test_finalise_source_credits_removes_all_duplicates_mixed_formats(self) -> None:
        source_url = "https://example.com/source"
        content = (
            "<!-- wp:paragraph -->\n"
            f"<p><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">Source</a></p>\n"
            "<!-- /wp:paragraph -->\n\n"
            f"<p><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">Source</a></p>\n\n"
            "<!-- wp:paragraph -->\n"
            f"<p><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">"
            "Link to original article</a></p>\n"
            "<!-- /wp:paragraph -->\n\n"
            f"<p><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">"
            "Link to original article</a></p>\n\n"
            "<!-- wp:paragraph -->\n"
            "<p>Body text.</p>\n"
            "<!-- /wp:paragraph -->\n"
        )
        updated = finalise_source_credits(content, source_url, primary_source=None)
        self.assertEqual(updated.count(">Source</a>"), 0)
        self.assertEqual(updated.count(">Link to original article</a>"), 1)
        self.assertTrue(updated.rstrip().endswith("<!-- /wp:paragraph -->"))

    def test_finalise_source_credits_no_source_when_primary_reliable(self) -> None:
        source_url = "https://example.com/source"
        primary = {"primary_source": {"url": "https://example.com/primary", "confidence": 0.9}}
        updated = finalise_source_credits("Body", source_url, primary)
        self.assertEqual(updated.count(">Source</a>"), 0)
        self.assertEqual(updated.count(">Link to original article</a>"), 1)

    def test_finalise_source_credits_source_present_when_primary_unreliable(self) -> None:
        source_url = "https://example.com/source"
        primary = {"primary_source": {"url": None, "confidence": 0.2}}
        updated = finalise_source_credits("Body", source_url, primary)
        self.assertEqual(updated.count(">Source</a>"), 0)
        self.assertEqual(updated.count(">Link to original article</a>"), 1)


if __name__ == "__main__":
    unittest.main()
