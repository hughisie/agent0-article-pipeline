import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import taxonomy_assigner
from taxonomy_assigner import assign_tags_and_category


def _build_tags() -> list[dict]:
    return [
        {"id": 100, "name": "Barcelona", "slug": "barcelona"},
        {"id": 101, "name": "Catalonia", "slug": "catalonia"},
        {"id": 102, "name": "Infrastructure", "slug": "infrastructure"},
        {"id": 103, "name": "Housing", "slug": "housing"},
        {"id": 104, "name": "Economy", "slug": "economy"},
    ]


def _build_categories() -> list[dict]:
    return [
        {"id": 1, "name": "News", "slug": "news"},
        {"id": 2, "name": "Politics", "slug": "politics"},
        {"id": 3, "name": "Transport", "slug": "transport"},
        {"id": 4, "name": "Housing", "slug": "housing"},
        {"id": 5, "name": "Economy", "slug": "economy"},
        {"id": 6, "name": "Culture", "slug": "culture"},
    ]


def _build_payload(category: dict) -> dict:
    return {
        "category": {
            "id": category["id"],
            "name": category["name"],
            "slug": category["slug"],
            "is_new": False,
        },
        "tags": [
            {"id": 100, "name": "Barcelona", "slug": "barcelona", "is_new": False},
            {"id": 101, "name": "Catalonia", "slug": "catalonia", "is_new": False},
            {"id": 102, "name": "Infrastructure", "slug": "infrastructure", "is_new": False},
            {"id": 103, "name": "Housing", "slug": "housing", "is_new": False},
            {"id": 104, "name": "Economy", "slug": "economy", "is_new": False},
        ],
        "notes": "Test harness payload.",
    }


def run_case(article: dict, analysis: dict, article_meta: dict, category: dict) -> None:
    wp_categories = _build_categories()
    wp_tags = _build_tags()
    api_keys = {"DEEPSEEK_API_KEY": "test-key"}

    payload = _build_payload(category)

    def fake_call_deepseek_chat(model_name: str, system_prompt: str, user_prompt: str, api_key: str) -> str:
        return json.dumps(payload)

    original_call = taxonomy_assigner.call_deepseek_chat
    taxonomy_assigner.call_deepseek_chat = fake_call_deepseek_chat
    try:
        result = assign_tags_and_category(
            article=article,
            analysis=analysis,
            primary_source={"primary_source": {"url": "https://example.com"}},
            article_meta=article_meta,
            wp_categories=wp_categories,
            wp_tags=wp_tags,
            api_keys=api_keys,
        )
    finally:
        taxonomy_assigner.call_deepseek_chat = original_call

    category_name = result["category"]["name"]
    category_id = result["category"]["id"]
    if category_name.lower() == "news":
        raise AssertionError("Category should not be 'News' for these test cases.")

    tag_names = [tag.get("name") for tag in result.get("tags", []) if tag.get("name")]
    wp_payload = {"categories": [category_id], "tags": [tag.get("id") for tag in result["tags"]]}

    print("\nTest case:")
    print(f"- Title: {article.get('title')}")
    print(f"- Primary keyword: {article_meta.get('primary_keyword')}")
    print(f"- Selected category: {category_name} (id {category_id})")
    print(f"- Selected tags: {', '.join(tag_names)}")
    print(f"- WordPress payload categories: {wp_payload.get('categories')}")


if __name__ == "__main__":
    cases = [
        {
            "article": {"title": "City council launches municipal survey", "main_content_body": "Body"},
            "analysis": {"core_topic": "Municipal survey"},
            "article_meta": {"primary_keyword": "municipal survey"},
            "category": {"id": 2, "name": "Politics", "slug": "politics"},
        },
        {
            "article": {"title": "Metro line upgrades approved", "main_content_body": "Body"},
            "analysis": {"core_topic": "Transport infrastructure"},
            "article_meta": {"primary_keyword": "metro upgrades"},
            "category": {"id": 3, "name": "Transport", "slug": "transport"},
        },
        {
            "article": {"title": "Rent pressures intensify across the city", "main_content_body": "Body"},
            "analysis": {"core_topic": "Housing affordability"},
            "article_meta": {"primary_keyword": "housing costs"},
            "category": {"id": 4, "name": "Housing", "slug": "housing"},
        },
    ]

    for case in cases:
        run_case(case["article"], case["analysis"], case["article_meta"], case["category"])
