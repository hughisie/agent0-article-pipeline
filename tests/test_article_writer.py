import unittest

from article_writer import build_gemini_article_prompt


class TestArticleWriterPrompt(unittest.TestCase):
    def test_prompt_includes_json(self):
        original = {"title": "Title", "main_content_body": "Body"}
        analysis = {"english_summary": "Summary"}
        primary = {"primary_source": {"url": "https://example.com"}}
        prompt = build_gemini_article_prompt(original, analysis, primary)

        self.assertIn("Title", prompt["user_message"])
        self.assertIn("Summary", prompt["user_message"])
        self.assertIn("https://example.com", prompt["user_message"])


if __name__ == "__main__":
    unittest.main()
