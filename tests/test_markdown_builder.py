import unittest

from file_loader import Article
from markdown_builder import build_research_markdown


class TestMarkdownBuilder(unittest.TestCase):
    def test_build_research_markdown_basic(self):
        article = Article(
            title="Test Title",
            original_title="Titulo",
            original_language="es",
            main_content_body="Contenido",
            date_time="2025-01-01",
            source_url="https://example.com",
            source_name="Example",
            keywords=["news", "test"],
            profile_name="Profile",
        )
        analysis = {
            "english_translation_full": "Full translation",
            "english_summary": "Summary",
            "core_topic": "Topic",
            "original_artifact_type": "press release",
            "probable_primary_publisher": "Agency",
            "artifact_description": "Description",
            "key_claims": ["Claim 1", "Claim 2"],
        }
        primary = {
            "primary_source": {
                "url": "https://source.gov/report",
                "title": "Report",
                "publisher_guess": "Gov",
                "type_guess": "report",
                "confidence": 0.7,
            },
            "alternatives": [
                {
                    "url": "https://source.gov/press",
                    "title": "Press",
                    "reason": "Official press",
                    "confidence": 0.5,
                }
            ],
        }

        result = build_research_markdown(article, analysis, primary)
        self.assertIn("# Article Metadata", result)
        self.assertIn("## English Translation (Full)", result)
        self.assertIn("## Primary Source", result)
        self.assertIn("Report", result)


if __name__ == "__main__":
    unittest.main()
