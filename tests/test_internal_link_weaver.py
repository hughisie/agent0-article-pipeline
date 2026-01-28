import unittest

from internal_link_weaver import weave_internal_links, ensure_internal_links_present, enforce_unique_internal_links


class TestInternalLinkWeaver(unittest.TestCase):
    def test_weave_internal_links_inserts_into_paragraph_blocks(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n<p>Intro paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Second paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Third paragraph.</p>\n<!-- /wp:paragraph -->\n"
        )
        related = [
            {"url": "https://barna.news/example-1", "anchor_text": "housing policy update"},
            {"url": "https://barna.news/example-2", "anchor_text": "transport expansion plan"},
        ]
        updated, report = weave_internal_links(content, related)
        self.assertIn("https://barna.news/example-1", updated)
        self.assertIn("https://barna.news/example-2", updated)
        self.assertIn("<!-- wp:paragraph -->", updated)
        self.assertTrue(len(report.inserted) >= 1)

    def test_ensure_internal_links_present_reinserts(self) -> None:
        content = "<!-- wp:paragraph -->\n<p>Body.</p>\n<!-- /wp:paragraph -->\n"
        related = [{"url": "https://barna.news/example-3", "anchor_text": "local economy report"}]
        updated, missing = ensure_internal_links_present(content, related)
        self.assertIn("https://barna.news/example-3", updated)
        self.assertEqual(missing, ["https://barna.news/example-3"])

    def test_enforce_unique_internal_links_unlinks_duplicates(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n"
            "<p>First <a href=\"https://barna.news/one\">link</a>.</p>\n"
            "<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n"
            "<p>Second <a href=\"https://barna.news/one\">link</a>.</p>\n"
            "<!-- /wp:paragraph -->\n"
        )
        updated = enforce_unique_internal_links(content)
        self.assertEqual(updated.count("https://barna.news/one"), 1)


if __name__ == "__main__":
    unittest.main()
