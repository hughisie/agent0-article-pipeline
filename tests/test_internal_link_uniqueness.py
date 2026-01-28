import unittest

from internal_link_weaver import weave_internal_links, enforce_unique_internal_links


class TestInternalLinkUniqueness(unittest.TestCase):
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
        self.assertIn("Second link.", updated)

    def test_weave_internal_links_uses_unique_templates(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n<p>Intro paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Second paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Third paragraph.</p>\n<!-- /wp:paragraph -->\n"
        )
        related = [
            {"url": "https://barna.news/a", "anchor_text": "topic A"},
            {"url": "https://barna.news/b", "anchor_text": "topic B"},
            {"url": "https://barna.news/c", "anchor_text": "topic C"},
        ]
        updated, _ = weave_internal_links(content, related)
        self.assertIn("topic A", updated)
        self.assertIn("topic B", updated)
        self.assertIn("topic C", updated)
        self.assertGreater(len(set([line for line in updated.splitlines() if "barna.news/" in line])), 1)

    def test_no_more_than_three_internal_links(self) -> None:
        content = (
            "<!-- wp:paragraph -->\n<p>Intro paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Second paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Third paragraph.</p>\n<!-- /wp:paragraph -->\n\n"
            "<!-- wp:paragraph -->\n<p>Fourth paragraph.</p>\n<!-- /wp:paragraph -->\n"
        )
        related = [
            {"url": "https://barna.news/a", "anchor_text": "topic A"},
            {"url": "https://barna.news/b", "anchor_text": "topic B"},
            {"url": "https://barna.news/c", "anchor_text": "topic C"},
            {"url": "https://barna.news/d", "anchor_text": "topic D"},
        ]
        updated, _ = weave_internal_links(content, related)
        self.assertLessEqual(updated.count("https://barna.news/"), 3)


if __name__ == "__main__":
    unittest.main()
