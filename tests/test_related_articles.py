import unittest
from unittest.mock import patch

from related_articles import find_related_articles


class TestRelatedArticles(unittest.TestCase):
    def test_find_related_articles_parses_json(self) -> None:
        recent_posts = [
            {"url": "https://barna.news/post-1", "title": "Post One", "excerpt": "Summary"},
            {"url": "https://barna.news/post-2", "title": "Post Two", "excerpt": "Summary"},
        ]
        payload = {
            "related": [
                {
                    "url": "https://barna.news/post-1",
                    "title": "Post One",
                    "anchor_text": "post one coverage",
                    "why_relevant": "Background context",
                    "suggested_insertion": "intro",
                }
            ]
        }
        with patch("related_articles.GeminiClient.generate", return_value=str(payload).replace("'", "\"")):
            result = find_related_articles(
                article={"title": "New story"},
                analysis={"core_topic": "Topic"},
                primary_source={},
                recent_posts=recent_posts,
                api_keys={"GEMINI_API_KEY": "test"},
            )
        self.assertEqual(len(result.get("related", [])), 1)
        self.assertEqual(result["related"][0]["url"], "https://barna.news/post-1")


if __name__ == "__main__":
    unittest.main()
