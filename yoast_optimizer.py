import json

from deepseek_client import call_deepseek_chat, DeepSeekError
from llm_clients import LLMError, parse_json_response
from config import load_config
from prompts import resolve_prompt


class YoastOptimizationError(Exception):
    pass


def build_yoast_prompt(
    article_meta: dict,
    wp_block_content: str,
    used_keyphrases: list[str],
    prompt_overrides: dict | None = None
) -> dict:
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

Your goal is to adjust the metadata and content so that Yoast SEO's content analysis scores GREEN on EVERY check:

CRITICAL SEO CHECKS (these are the most commonly failing):
  1. KEYPHRASE LENGTH: Maximum 4 content words. If current keyphrase has 5+ words, SHORTEN it.
     Example: 'human smuggling fugitive arrested Manlleu' → 'smuggling fugitive arrested Manlleu'
  2. KEYPHRASE IN SEO TITLE: The exact keyphrase MUST be the FIRST WORDS of the meta_title.
     Example: If keyphrase is 'Barcelona crime rates', title must START with 'Barcelona Crime Rates: ...'
  3. SEO TITLE WIDTH: Max 55 characters. If longer, shorten it.
  4. META DESCRIPTION LENGTH: 120-150 characters. NEVER exceed 155 characters.
  5. KEYPHRASE IN INTRODUCTION: The exact keyphrase MUST appear in the FIRST paragraph of the article body.
     If it doesn't, rewrite the first paragraph to naturally include it.
  6. KEYPHRASE DENSITY: The exact keyphrase must appear 3-6 times in the article body.
     If density is too low, naturally weave the keyphrase into 1-2 more sentences. Do NOT force it into every paragraph.
  7. KEYPHRASE IN SUBHEADINGS: At least one H2 heading must contain the keyphrase.
  8. KEYPHRASE IN IMAGE ALT: If there are <img> tags, at least one must have an alt attribute containing the keyphrase.
  9. KEYPHRASE IN SLUG: The slug must contain the keyphrase words.
  10. TEXT LENGTH: Article must be at least 400 words. If shorter, expand with relevant details.

READABILITY CHECKS (EQUALLY CRITICAL — these must also score GREEN):
  11. PASSIVE VOICE: Must be under 10% of sentences. ACTIVELY REWRITE every passive sentence:
      - 'The station was evacuated by firefighters' → 'Firefighters evacuated the station'
      - 'The report was published yesterday' → 'The council published the report yesterday'
      - 'Residents were told to stay indoors' → 'Authorities told residents to stay indoors'
      - 'The decision was made after a meeting' → 'Officials made the decision after a meeting'
      - RULE: If the agent is missing, NAME one (police, officials, authorities, the council, organisers)
  12. SENTENCE LENGTH: At least 75% of sentences must be UNDER 20 words. Split long sentences:
      - Split at conjunctions (and, but, while, which, who)
      - Turn subordinate clauses into separate sentences
      - Remove unnecessary qualifiers and filler words
      - Example: 'The fire broke out at the station on Monday afternoon and was quickly extinguished by emergency services who arrived within minutes.' (25 words)
        → 'The fire broke out on Monday afternoon. Emergency services arrived within minutes and extinguished the blaze.' (7+10 words)
  13. TRANSITION WORDS: Must appear in 30-45% of sentences (NOT more than 45%!):
      however, meanwhile, therefore, additionally, moreover, consequently
      - NEVER start more than 2 consecutive sentences with transition words
      - NEVER use the same transition word twice in one section
      - If transition word usage is ABOVE 45%, REMOVE excess transition words to sound natural
      - BAD: 'Consequently, X. Furthermore, Y. Moreover, Z. Additionally, W.' (robotic)
      - GOOD: 'X happened. Consequently, Y occurred. Z followed. Moreover, W emerged.' (natural)
  14. Previously used keyphrase: choose a keyphrase not exactly used before

Additionally:
  - Maintain exactly one H1 heading.
  - Keep the tone as a neutral, professional British news article.
  - Do not introduce invented facts or fake statistics.
  - Do not remove or alter internal links to the site's own domain; preserve all existing <a> tags exactly.
  - Do NOT add generic resource sentences like "For more information, visit X" or "You can learn more about X from Y" or "For broader context, see this report".
  - Do NOT add links to Wikipedia, WHO, World Bank, European Central Bank, British Museum, or other generic authoritative sources unless they are directly cited in the original article.
  - You may adjust or insert image alt attributes to include the keyphrase, but keep alt text meaningful.
  - Prefer shorter sentences. Only add transition words if usage is below 30%.
  - If transition words exceed 45%, REMOVE some to avoid robotic writing.
  - NEVER start 3+ consecutive sentences with transition words.
  - Do NOT repeat the keyphrase in every paragraph or every H2. Use it in intro, one H2, and 1-2 body paragraphs.
  - Vary sentence openers: mix subject-first, time-first, place-first, and transition-word openers.

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

    system_prompt = resolve_prompt(prompt_overrides, "PROMPT_YOAST_SYSTEM", system_prompt)
    user_prompt = resolve_prompt(prompt_overrides, "PROMPT_YOAST_USER", user_prompt)

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

    prompt = build_yoast_prompt(article_meta, wp_block_content, used_keyphrases, prompt_overrides=api_keys)

    for attempt in range(2):
        try:
            raw = call_deepseek_chat(deepseek_model, prompt["system_prompt"], prompt["user_prompt"], api_key)
            payload = parse_json_response(raw)
            return _validate_payload(payload)
        except (DeepSeekError, LLMError, YoastOptimizationError):
            if attempt == 1:
                raise
