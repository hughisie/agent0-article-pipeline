import unittest
from unittest.mock import patch

import wordpress_client


class FakeResponse:
    def __init__(self, status_code: int, json_data: list, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class TestWordPressClient(unittest.TestCase):
    def test_get_recent_posts_shape(self) -> None:
        posts = [
            {
                "id": 1,
                "title": {"rendered": "Post One"},
                "link": "https://barna.news/post-1",
                "date": "2026-01-01T10:00:00",
                "excerpt": {"rendered": "<p>Excerpt</p>"},
                "content": {"rendered": "<p>Content body</p>"},
                "categories": [10],
                "tags": [20],
            }
        ]
        with patch("wordpress_client.get_wp_categories", return_value=[{"id": 10, "name": "Politics"}]), patch(
            "wordpress_client.get_wp_tags", return_value=[{"id": 20, "name": "Barcelona"}]
        ), patch(
            "wordpress_client.requests.get", return_value=FakeResponse(200, posts)
        ):
            result = wordpress_client.get_recent_posts("https://barna.news", "u", "p", months_back=3, max_posts=1)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIn("title", item)
        self.assertIn("url", item)
        self.assertIn("excerpt", item)
        self.assertEqual(item["categories"], ["Politics"])
        self.assertEqual(item["tags"], ["Barcelona"])


if __name__ == "__main__":
    unittest.main()
