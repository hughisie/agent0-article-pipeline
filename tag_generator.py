import json

from config import load_config
from deepseek_client import call_deepseek_chat, DeepSeekError
from llm_clients import LLMError, parse_json_response
from prompts import resolve_prompt


class TagGenerationError(Exception):
    pass


def _normalise_tag_value(value: str | None) -> str:
    return (value or "").strip().lower()


def build_tag_generation_prompt(
    article: dict,
    existing_tags: list[dict],
    prompt_overrides: dict | None = None
) -> dict:
    system_prompt = (
        "You are an editorial taxonomy assistant for an online news site. "
        "You respond ONLY with valid JSON."
    )
    user_prompt = """
You will receive an article object (title, body, metadata) and a list of existing WordPress tags.

Task:
- Suggest 5-7 concise, high-quality tags that reflect the article's core topic, places, entities, and themes.
- Prefer existing tags when they match.
- Do not include duplicates or near-duplicates.
- Use British English unless the tag is a proper noun.

Return ONLY JSON in this exact structure:
{
  "tags": [
    {"name": "Barcelona"},
    {"name": "Taxi drivers"}
  ]
}

Article JSON:
<ARTICLE_JSON_HERE>

Existing tags:
<WP_TAGS_JSON_HERE>
"""
    user_prompt = user_prompt.replace(
        "<ARTICLE_JSON_HERE>", json.dumps(article, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace(
        "<WP_TAGS_JSON_HERE>", json.dumps(existing_tags, ensure_ascii=False, indent=2)
    )

    system_prompt = resolve_prompt(prompt_overrides, "PROMPT_TAG_GEN_SYSTEM", system_prompt)
    user_prompt = resolve_prompt(prompt_overrides, "PROMPT_TAG_GEN_USER", user_prompt)

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def generate_tags_from_article(
    article: dict,
    existing_tags: list[dict],
    model_name: str = "deepseek-chat",
    api_keys: dict | None = None,
) -> list[dict]:
    config = api_keys or load_config()
    api_key = config.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise TagGenerationError("DEEPSEEK_API_KEY is required for tag generation")

    prompt = build_tag_generation_prompt(article, existing_tags, prompt_overrides=api_keys)

    try:
        raw = call_deepseek_chat(model_name, prompt["system_prompt"], prompt["user_prompt"], api_key)
        payload = parse_json_response(raw)
    except (DeepSeekError, LLMError) as exc:
        raise TagGenerationError(str(exc)) from exc

    tags = payload.get("tags")
    if not isinstance(tags, list):
        raise TagGenerationError("Expected tags list in response")

    cleaned = []
    seen = set()
    for tag in tags:
        name = (tag or {}).get("name")
        if not name:
            continue
        normalised = _normalise_tag_value(name)
        if not normalised or normalised in seen:
            continue
        seen.add(normalised)
        cleaned.append({"name": name})

    if len(cleaned) < 5:
        raise TagGenerationError("Expected at least 5 tags from LLM")
    if len(cleaned) > 7:
        cleaned = cleaned[:7]
    return cleaned
