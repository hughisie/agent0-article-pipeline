import json
import unittest
from unittest.mock import patch

from taxonomy_assigner import assign_tags_and_category


def _build_payload(category_id: int, name: str, slug: str) -> dict:
    return {
        "category": {"id": category_id, "name": name, "slug": slug, "is_new": False},
        "tags": [
            {"id": 10, "name": "Barcelona", "slug": "barcelona", "is_new": False},
            {"id": 11, "name": "City council", "slug": "city-council", "is_new": False},
            {"id": 12, "name": "Survey", "slug": "survey", "is_new": False},
            {"id": 13, "name": "Public opinion", "slug": "public-opinion", "is_new": False},
            {"id": 14, "name": "Local government", "slug": "local-government", "is_new": False},
        ],
        "notes": "Test payload.",
    }


class TestTaxonomyAssigner(unittest.TestCase):
    def setUp(self) -> None:
        self.article = {"title": "City survey released", "main_content_body": "Body"}
        self.analysis = {"core_topic": "Municipal survey"}
        self.primary = {"primary_source": {"url": "https://example.com"}}
        self.article_meta = {
            "meta_title": "Survey results",
            "meta_description": "Summary",
            "primary_keyword": "municipal survey",
            "slug": "survey-results",
        }
        self.wp_categories = [
            {"id": 1, "name": "News", "slug": "news"},
            {"id": 2, "name": "Politics", "slug": "politics"},
            {"id": 3, "name": "Transport", "slug": "transport"},
        ]
        self.wp_tags = [
            {"id": 10, "name": "Barcelona", "slug": "barcelona"},
            {"id": 11, "name": "City council", "slug": "city-council"},
        ]
        self.api_keys = {"DEEPSEEK_API_KEY": "test-key"}

    def test_retries_on_generic_category(self) -> None:
        news_payload = _build_payload(1, "News", "news")
        transport_payload = _build_payload(3, "Transport", "transport")
        with patch(
            "taxonomy_assigner.call_deepseek_chat",
            side_effect=[json.dumps(news_payload), json.dumps(transport_payload)],
        ) as mock_call:
            with patch("builtins.print") as mock_print:
                result = assign_tags_and_category(
                    article=self.article,
                    analysis=self.analysis,
                    primary_source=self.primary,
                    article_meta=self.article_meta,
                    wp_categories=self.wp_categories,
                    wp_tags=self.wp_tags,
                    api_keys=self.api_keys,
                )
        self.assertEqual(result["category"]["id"], 3)
        self.assertEqual(mock_call.call_count, 2)
        self.assertTrue(
            any("generic category" in str(call.args[0]) for call in mock_print.call_args_list)
        )

    def test_accepts_generic_after_retry(self) -> None:
        news_payload = _build_payload(1, "News", "news")
        with patch(
            "taxonomy_assigner.call_deepseek_chat",
            side_effect=[json.dumps(news_payload), json.dumps(news_payload)],
        ) as mock_call:
            with patch("builtins.print") as mock_print:
                result = assign_tags_and_category(
                    article=self.article,
                    analysis=self.analysis,
                    primary_source=self.primary,
                    article_meta=self.article_meta,
                    wp_categories=self.wp_categories,
                    wp_tags=self.wp_tags,
                    api_keys=self.api_keys,
                )
        self.assertEqual(result["category"]["id"], 1)
        self.assertEqual(mock_call.call_count, 2)
        self.assertTrue(
            any("last-resort" in str(call.args[0]) for call in mock_print.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
