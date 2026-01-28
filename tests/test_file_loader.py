import json
import tempfile
import unittest
from pathlib import Path

from file_loader import load_article


class TestFileLoader(unittest.TestCase):
    def test_load_json(self):
        data = {
            "title": "Title",
            "main_content_body": "Body",
            "keywords": ["a", "b"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "article.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            article = load_article(str(path))

        self.assertEqual(article.title, "Title")
        self.assertEqual(article.main_content_body, "Body")
        self.assertEqual(article.keywords, ["a", "b"])

    def test_load_markdown_with_front_matter(self):
        content = """---
title: Example Title
original_language: es
keywords: alpha, beta
---
Body content here.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "article.md"
            path.write_text(content, encoding="utf-8")
            article = load_article(str(path))

        self.assertEqual(article.title, "Example Title")
        self.assertEqual(article.original_language, "es")
        self.assertIn("Body content", article.main_content_body)
        self.assertEqual(article.keywords, ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
