import unittest

from yoast_optimizer import build_yoast_prompt


class TestYoastOptimizer(unittest.TestCase):
    def test_yoast_optimizer_preserves_links(self) -> None:
        prompt = build_yoast_prompt(
            article_meta={"meta_title": "Title"},
            wp_block_content="<!-- wp:paragraph --><p>Body</p><!-- /wp:paragraph -->",
            used_keyphrases=[],
        )
        self.assertIn("Do not remove or alter internal links", prompt["user_prompt"])


if __name__ == "__main__":
    unittest.main()
