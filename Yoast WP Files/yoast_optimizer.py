import json

from deepseek_client import call_deepseek_chat, DeepSeekError
from llm_clients import LLMError, parse_json_response
from config import load_config


class YoastOptimizationError(Exception):
    pass


def build_yoast_prompt(article_meta: dict, wp_block_content: str, used_keyphrases: list[str]) -> dict:
    system_prompt = (
        "You are an expert SEO editor familiar with Yoast SEO's content analysis.\n"
        "You write in British English and adjust articles to achieve a 100% Yoast SEO score.\n"
        "You must preserve the factual meaning and tone but are allowed to slightly rewrite text for SEO and clarity.\n"
        "You output ONLY valid JSON and no extra commentary. Do not add inline images; rely on the featured image alt text if needed."
    )

    user_prompt = """
You will receive:
  1. The current SEO metadata for a WordPress article (meta_title, meta_description, primary_keyword, slug, tags, excerpt).
  2. The full article body as Gutenberg block markup (WordPress block content).
  3. A list of focus keyphrases previously used on this site.

Your goal is to adjust the metadata and content so that Yoast SEO's content analysis would give a perfect (green) score for the following checks:
  - Outbound links
  - Keyphrase in image alt attributes
  - Keyphrase in introduction
  - Keyphrase density
  - Keyphrase in SEO title (at the beginning)
  - Keyphrase length (sensible length, not empty)
  - Keyphrase in meta description
  - Meta description length
  - Previously used keyphrase (choose a keyphrase not exactly used before)
  - Keyphrase in slug
  - Keyphrase in subheadings
  - Passive voice under 10% (prefer active voice)
  - Sentence length: keep most sentences under 20 words
  - Transition words: raise usage to above 35%

Additionally:
  - Maintain exactly one H1 heading.
  - Keep the tone as a neutral, professional British news article.
  - Do not introduce invented facts or fake statistics.
  - Do not remove or alter internal links to the site's own domain; preserve all existing <a> tags exactly.
  - You may add or refine outbound links to authoritative external sources where genuinely relevant.
  - You may adjust or insert image alt attributes to include the keyphrase, but keep alt text meaningful.
  - Prefer shorter sentences and add clear transition words (however, meanwhile, therefore, in addition).

Make minimal structural changes to the Gutenberg blocks. Prefer editing the text inside blocks rather than reflowing the entire structure.

Return ONLY JSON with this structure:

{
  "meta_title": "...",
  "meta_description": "...",
  "primary_keyword": "...",
  "slug": "...",
  "tags": ["...", "..."],
  "excerpt": "...",
  "wp_block_content": "...",
  "yoast_notes": "Brief explanation of what was changed for SEO."
}

Here is the metadata JSON:
<ARTICLE_META_JSON_HERE>

Here is the Gutenberg block content:
<WP_BLOCK_CONTENT_HERE>

Here is the list of previously used keyphrases:
<USED_KEYPHRASES_JSON_HERE>
"""

    user_prompt = user_prompt.replace(
        "<ARTICLE_META_JSON_HERE>", json.dumps(article_meta, ensure_ascii=False, indent=2)
    )
    user_prompt = user_prompt.replace("<WP_BLOCK_CONTENT_HERE>", wp_block_content)
    user_prompt = user_prompt.replace(
        "<USED_KEYPHRASES_JSON_HERE>", json.dumps(used_keyphrases, ensure_ascii=False, indent=2)
    )

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def _validate_payload(payload: dict) -> dict:
    required = [
        "meta_title",
        "meta_description",
        "primary_keyword",
        "slug",
        "tags",
        "excerpt",
        "wp_block_content",
        "yoast_notes",
    ]
    for key in required:
        if key not in payload:
            raise YoastOptimizationError(f"Missing key in Yoast payload: {key}")
    if not isinstance(payload.get("tags"), list):
        raise YoastOptimizationError("Expected 'tags' to be a list")
    return payload


def optimise_for_yoast(
    article_meta: dict,
    wp_block_content: str,
    used_keyphrases: list[str],
    deepseek_model: str = "deepseek-chat",
    api_keys: dict | None = None,
) -> dict:
    config = api_keys or load_config()
    api_key = config.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise YoastOptimizationError("DEEPSEEK_API_KEY is required for Yoast optimisation")

    prompt = build_yoast_prompt(article_meta, wp_block_content, used_keyphrases)

    for attempt in range(2):
        try:
            raw = call_deepseek_chat(deepseek_model, prompt["system_prompt"], prompt["user_prompt"], api_key)
            payload = parse_json_response(raw)
            return _validate_payload(payload)
        except (DeepSeekError, LLMError, YoastOptimizationError):
            if attempt == 1:
                raise
