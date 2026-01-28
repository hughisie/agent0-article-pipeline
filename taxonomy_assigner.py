import json

from deepseek_client import call_deepseek_chat, DeepSeekError
from llm_clients import LLMError, parse_json_response
from config import load_config
from prompts import resolve_prompt


class TaxonomyAssignmentError(Exception):
    pass


def build_taxonomy_prompt(
    article: dict,
    analysis: dict,
    primary_source: dict,
    article_meta: dict,
    wp_categories: list[dict],
    wp_tags: list[dict],
    strict_generic_avoidance: bool = False,
    prompt_overrides: dict | None = None,
) -> dict:
    system_prompt = (
        "You are an editorial taxonomy expert for an online news site.\n"
        "You speak British English.\n"
        "You assign categories and tags to news articles so they are:\n"
        "  - consistent with existing site taxonomies, and\n"
        "  - useful for readers and SEO.\n"
        "You respond ONLY with valid JSON and no extra commentary."
    )

    extra_guidance = ""
    if strict_generic_avoidance:
        extra_guidance = (
            "\nAdditional instruction:\n"
            "  - Never choose generic categories such as \"News\", \"General\", or \"Latest\" if any "
            "more specific category exists in the provided list.\n"
            "  - Use those generic categories only if no other category reasonably applies.\n"
        )

    user_prompt = """
You will receive:
  1. An article object (title, body, metadata).
  2. A translation and analysis object summarising the article.
  3. A primary source object indicating what official document or event the article is based on.
  4. SEO metadata (primary keyword, title, summary).
  5. Existing WordPress categories.
  6. Existing WordPress tags.

Your tasks:
  - Pick the single best primary category for this article from the existing categories list.
  - When selecting the category:
    - You must choose the single most specific, relevant category from the existing list.
    - Avoid generic categories such as "News" or "General" unless absolutely no other category fits.
    - If there is a category explicitly related to the topic (e.g. "Barcelona", "Politics", "Transport", "Housing"), prefer that over broad catch-alls.
    - You may NOT invent new category names; you must select from the provided list.
    - If more than one category seems relevant, pick the one that best reflects the primary angle of the story.
    - Pick exactly one category.
  - Suggest 5-7 tags:
    - Prefer reusing existing tags where the meaning matches.
    - Avoid duplicates and near-duplicates.
    - Only introduce a new tag when it clearly adds value and doesn't already exist under a different name.
    - Tags should be short, human-readable phrases or keywords.
    - The choices should reflect the article's core topic, key entities (places, people, organisations), and themes.

Constraints:
  - Category MUST be chosen from the existing categories: do not invent a new category name.
  - Tags may be a mix of existing and new tags.
  - Use British English spelling unless the tag is a proper noun.
<EXTRA_GUIDANCE_HERE>

Return ONLY JSON in this exact structure:

{
  "category": {
    "id": 123,
    "name": "Politics",
    "slug": "politics",
    "is_new": false
  },
  "tags": [
    {
      "id": 456,
      "name": "Barcelona",
      "slug": "barcelona",
      "is_new": false
    },
    {
      "id": null,
      "name": "Municipal barometer",
      "slug": null,
      "is_new": true
    }
  ],
  "notes": "Short explanation of why this category and these tags were chosen."
}

If there are no suitable existing tags, you may set all tag id and slug fields to null and mark is_new as true.

Here is the Article JSON:
<ARTICLE_JSON_HERE>

Here is the Analysis JSON:
<ANALYSIS_JSON_HERE>

Here is the Primary Source JSON:
<PRIMARY_SOURCE_JSON_HERE>

Here is the SEO metadata JSON:
<ARTICLE_META_JSON_HERE>

Here is the list of existing WordPress categories:
<WP_CATEGORIES_JSON_HERE>

Here is the list of existing WordPress tags:
<WP_TAGS_JSON_HERE>
"""

    user_prompt = user_prompt.replace("<EXTRA_GUIDANCE_HERE>", extra_guidance)
    user_prompt = user_prompt.replace(
        "<ARTICLE_JSON_HERE>", json.dumps(article, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<ANALYSIS_JSON_HERE>", json.dumps(analysis, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<PRIMARY_SOURCE_JSON_HERE>", json.dumps(primary_source, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<ARTICLE_META_JSON_HERE>", json.dumps(article_meta, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<WP_CATEGORIES_JSON_HERE>", json.dumps(wp_categories, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<WP_TAGS_JSON_HERE>", json.dumps(wp_tags, ensure_ascii=False, indent=2)
    )

    system_prompt = resolve_prompt(prompt_overrides, "PROMPT_TAXONOMY_SYSTEM", system_prompt)
    user_prompt = resolve_prompt(prompt_overrides, "PROMPT_TAXONOMY_USER", user_prompt)

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def _validate_payload(payload: dict) -> dict:
    if "category" not in payload or payload.get("category") is None:
        raise TaxonomyAssignmentError("Missing category in taxonomy payload")
    if "tags" not in payload or payload.get("tags") is None:
        raise TaxonomyAssignmentError("Missing tags in taxonomy payload")

    tags = payload.get("tags")
    if not isinstance(tags, list):
        raise TaxonomyAssignmentError("Expected tags to be a list")

    if len(tags) < 5:
        raise TaxonomyAssignmentError("Expected at least 5 tags from taxonomy assignment")
    if len(tags) > 7:
        payload["tags"] = tags[:7]

    return payload


def _normalise_category_value(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_generic_category(category: dict | None) -> bool:
    if not category:
        return False
    generic = {"news", "general", "latest", "uncategorized"}
    name = _normalise_category_value(category.get("name"))
    slug = _normalise_category_value(category.get("slug"))
    return name in generic or slug in generic


def _has_non_generic_categories(wp_categories: list[dict]) -> bool:
    return any(not _is_generic_category(category) for category in wp_categories or [])


def _resolve_category(payload_category: dict, wp_categories: list[dict]) -> dict:
    if not isinstance(payload_category, dict):
        raise TaxonomyAssignmentError("Category must be an object")
    category_id = payload_category.get("id")
    if category_id is not None:
        for category in wp_categories or []:
            if category.get("id") == category_id:
                return category
    name_norm = _normalise_category_value(payload_category.get("name"))
    slug_norm = _normalise_category_value(payload_category.get("slug"))
    for category in wp_categories or []:
        if name_norm and name_norm == _normalise_category_value(category.get("name")):
            return category
        if slug_norm and slug_norm == _normalise_category_value(category.get("slug")):
            return category
    raise TaxonomyAssignmentError("Selected category not found in WordPress categories list")


def _validate_and_normalise_category(payload: dict, wp_categories: list[dict]) -> dict:
    resolved = _resolve_category(payload.get("category"), wp_categories)
    payload["category"] = {
        "id": resolved.get("id"),
        "name": resolved.get("name"),
        "slug": resolved.get("slug"),
        "is_new": False,
    }
    if not payload["category"]["id"]:
        raise TaxonomyAssignmentError("Selected category missing ID")
    return payload


def assign_tags_and_category(
    article: dict,
    analysis: dict,
    primary_source: dict,
    article_meta: dict,
    wp_categories: list[dict],
    wp_tags: list[dict],
    model_name: str = "deepseek-chat",
    api_keys: dict | None = None,
) -> dict:
    config = api_keys or load_config()
    api_key = config.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise TaxonomyAssignmentError("DEEPSEEK_API_KEY is required for taxonomy assignment")
    last_error = None

    for attempt in range(2):
        prompt = build_taxonomy_prompt(
            article,
            analysis,
            primary_source,
            article_meta,
            wp_categories,
            wp_tags,
            strict_generic_avoidance=attempt == 1,
            prompt_overrides=api_keys,
        )
        try:
            raw = call_deepseek_chat(model_name, prompt["system_prompt"], prompt["user_prompt"], api_key)
            payload = parse_json_response(raw)
            payload = _validate_payload(payload)
            payload = _validate_and_normalise_category(payload, wp_categories)
            if _is_generic_category(payload.get("category")) and _has_non_generic_categories(wp_categories):
                if attempt == 0:
                    print("Warning: LLM selected a generic category; retrying with stricter prompt.")
                    continue
                print("Warning: LLM still selected a generic category; accepting as last-resort fallback.")
            else:
                # Category assignment is LLM-driven; generic categories are avoided unless unavoidable.
                print(
                    f"Taxonomy assignment succeeded: category '{payload['category'].get('name')}' "
                    f"(id {payload['category'].get('id')})."
                )
            return payload
        except (DeepSeekError, LLMError, TaxonomyAssignmentError) as exc:
            last_error = exc
            if attempt == 1:
                raise
    if last_error:
        raise last_error
