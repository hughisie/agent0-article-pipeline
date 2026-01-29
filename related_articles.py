import json

from llm_clients import GeminiClient, LLMError, parse_json_response
from prompts import resolve_prompt


def build_related_articles_prompt(
    article: dict,
    analysis: dict,
    primary_source: dict,
    recent_posts: list[dict],
    strict: bool = False,
    prompt_overrides: dict | None = None,
) -> dict:
    system_message = (
        "You are an editorial assistant working on an online news site.\n"
        "You speak British English.\n"
        "You help identify related articles from the site's recent coverage and suggest natural ways to reference them inside a new article.\n"
        "You always respond with valid JSON and no extra commentary."
    )

    article_payload = {
        "article": article,
        "analysis": analysis,
    }

    extra_rules = ""
    if strict:
        extra_rules = (
            "\nStrict requirements:\n"
            "  - If at least 10 candidates are provided, you must select at least one related link.\n"
            "  - Only select URLs from the candidate list exactly as provided.\n"
        )

    user_message = (
        "You will receive:\n"
        "  1. JSON describing a new story's article metadata and key analysis.\n"
        "  2. JSON describing its primary source.\n"
        "  3. A list of recent articles from the same site (title, URL, date, summary).\n\n"
        "Tasks:\n"
        "  - Identify 1-3 related articles that provide useful background, context, or continuation.\n"
        "  - Provide descriptive anchor text, a brief relevance note, and insertion placement.\n"
        "  - Prefer topical diversity; do not pick multiple links on the exact same subtopic.\n\n"
        "CRITICAL RELEVANCE REQUIREMENTS:\n"
        "  - Related articles MUST share the same core topic, policy area, or subject matter as the new article.\n"
        "  - Geographic or institutional proximity alone is NOT sufficient for relevance.\n"
        "  - Examples of GOOD relevance:\n"
        "    * New article about terrace heaters → Related: previous articles about terrace heater regulations, outdoor heating policies\n"
        "    * New article about metro expansion → Related: previous metro construction updates, public transport infrastructure\n"
        "  - Examples of BAD relevance (DO NOT LINK):\n"
        "    * New article about terrace heaters → DON'T link to: train evacuations, bureaucracy reforms, unrelated government announcements\n"
        "    * New article about beach rules → DON'T link to: traffic regulations, housing policies\n"
        "  - Ask yourself: \"Would a reader interested in THIS specific topic find THAT article genuinely useful?\"\n"
        "  - If the connection requires mental gymnastics or creative interpretation, DO NOT SELECT IT.\n"
        "  - Semantic topic overlap is REQUIRED: both articles must discuss the same industry, regulation type, or specific issue.\n"
        "  - It is better to return ZERO links than to return irrelevant ones.\n\n"
        "Constraints:\n"
        "  - Prefer articles from the last 2-3 months.\n"
        "  - You MAY choose older posts ONLY if they are clearly part of the same series or direct follow-up.\n"
        "  - URLs must be unique; do not repeat the same URL.\n"
        "  - Do not pick more than 3 total.\n"
        "  - The sentences must flow naturally in a neutral news style and refer to the site as \"we\" only if the original article clearly does so. Otherwise keep it impersonal.\n\n"
        "Return ONLY valid JSON in this exact structure:\n\n"
        "{\n"
        "  \"related\": [\n"
        "    {\n"
        "      \"url\": \"string\",\n"
        "      \"title\": \"string\",\n"
        "      \"anchor_text\": \"string\",\n"
        "      \"why_relevant\": \"string\",\n"
        "      \"suggested_insertion\": \"intro\" | \"mid\" | \"later\",\n"
        "      \"style\": \"context\" | \"background\" | \"continue\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "If you cannot find any truly relevant article with strong semantic topic overlap, return an empty related list.\n\n"
        "NEW STORY (article + analysis):\n"
        "<ARTICLE_AND_ANALYSIS_JSON_HERE>\n\n"
        "PRIMARY SOURCE:\n"
        "<PRIMARY_SOURCE_JSON_HERE>\n\n"
        "RECENT POSTS:\n"
        "<RECENT_POSTS_JSON_HERE>"
        + extra_rules
    )

    user_message = user_message.replace(
        "<ARTICLE_AND_ANALYSIS_JSON_HERE>", json.dumps(article_payload, ensure_ascii=False, indent=2)
    )
    user_message = user_message.replace(
        "<PRIMARY_SOURCE_JSON_HERE>", json.dumps(primary_source, ensure_ascii=False, indent=2)
    )
    user_message = user_message.replace(
        "<RECENT_POSTS_JSON_HERE>", json.dumps(recent_posts, ensure_ascii=False, indent=2)
    )

    system_message = resolve_prompt(prompt_overrides, "PROMPT_RELATED_SYSTEM", system_message)
    user_message = resolve_prompt(prompt_overrides, "PROMPT_RELATED_USER", user_message)
    return {"system_message": system_message, "user_message": user_message}


def _validate_related_payload(payload: dict, candidate_urls: set[str]) -> dict:
    related = payload.get("related") or []
    if not isinstance(related, list):
        related = []
    cleaned = []
    seen = set()
    for item in related:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url or url not in candidate_urls:
            continue
        if url in seen:
            continue
        anchor_text = (item.get("anchor_text") or "").strip()
        if not anchor_text:
            continue
        cleaned.append(
            {
                "url": url,
                "title": item.get("title"),
                "anchor_text": anchor_text,
                "why_relevant": item.get("why_relevant"),
                "suggested_insertion": item.get("suggested_insertion") or "mid",
                "style": item.get("style") or "context",
            }
        )
        seen.add(url)
        if len(cleaned) >= 3:
            break
    return {"related": cleaned}


def find_related_articles(
    article: dict,
    analysis: dict,
    primary_source: dict,
    recent_posts: list[dict],
    model_name: str = "gemini-2.0-flash-exp",
    api_keys: dict | None = None,
) -> dict:
    if not api_keys or not api_keys.get("GEMINI_API_KEY"):
        raise LLMError("GEMINI_API_KEY is required for related article selection")

    candidate_urls = {item.get("url") for item in recent_posts or [] if item.get("url")}
    prompt = build_related_articles_prompt(
        article, analysis, primary_source, recent_posts, prompt_overrides=api_keys
    )
    client = GeminiClient(api_key=api_keys["GEMINI_API_KEY"], model=model_name)

    for attempt in range(2):
        raw = client.generate(prompt["system_message"], prompt["user_message"], timeout=180)
        try:
            payload = parse_json_response(raw)
            cleaned = _validate_related_payload(payload, candidate_urls)
            if attempt == 0 and not cleaned.get("related") and len(candidate_urls) >= 10:
                prompt = build_related_articles_prompt(
                    article, analysis, primary_source, recent_posts, strict=True, prompt_overrides=api_keys
                )
                continue
            return cleaned
        except LLMError:
            if attempt == 1:
                raise
