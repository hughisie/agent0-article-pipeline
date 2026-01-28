import json

from config import load_config
from deepseek_client import call_deepseek_chat, DeepSeekError
from llm_clients import LLMError, parse_json_response


class InternalLinkSelectionError(Exception):
    pass


def _validate_payload(payload: dict, candidate_urls: set[str]) -> dict:
    related = payload.get("related") or []
    if not isinstance(related, list):
        related = []
    cleaned = []
    seen = set()
    for item in related:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url or url not in candidate_urls or url in seen:
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


def select_internal_links_deepseek(
    article: dict,
    analysis: dict,
    candidates: list[dict],
    model_name: str = "deepseek-chat",
    api_keys: dict | None = None,
) -> dict:
    config = api_keys or load_config()
    api_key = config.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise InternalLinkSelectionError("DEEPSEEK_API_KEY is required for internal link selection")

    candidate_urls = {item.get("url") for item in candidates or [] if item.get("url")}

    system_prompt = (
        "You are an editorial assistant for internal linking on a news site. "
        "You respond ONLY with valid JSON."
    )
    user_prompt = """
You will receive:
  1) A new story (article + analysis).
  2) A list of candidate internal articles with URL, title, excerpt, date, categories, and tags.

Task:
  - Select 1-3 unique internal articles to link in the new story.
  - Prefer topical diversity; do not pick multiple links about the exact same subtopic.
  - Use only the URLs provided in the candidate list.
  - Provide descriptive anchor text and a short relevance note.
  - Suggest placement: intro, mid, or later.

Return ONLY JSON in this exact structure:
{
  "related": [
    {
      "url": "string",
      "title": "string",
      "anchor_text": "string",
      "why_relevant": "string",
      "suggested_insertion": "intro|mid|later",
      "style": "context|background|continue"
    }
  ]
}

NEW STORY (article + analysis):
<ARTICLE_JSON_HERE>

CANDIDATE POSTS:
<CANDIDATES_JSON_HERE>
"""
    user_prompt = user_prompt.replace(
        "<ARTICLE_JSON_HERE>",
        json.dumps({"article": article, "analysis": analysis}, ensure_ascii=False, indent=2),
    )
    user_prompt = user_prompt.replace(
        "<CANDIDATES_JSON_HERE>", json.dumps(candidates, ensure_ascii=False, indent=2)
    )

    for attempt in range(2):
        try:
            raw = call_deepseek_chat(model_name, system_prompt, user_prompt, api_key)
            payload = parse_json_response(raw)
            cleaned = _validate_payload(payload, candidate_urls)
            if attempt == 0 and not cleaned.get("related") and len(candidate_urls) >= 10:
                user_prompt = user_prompt + "\nIf candidates exist, you must select at least one."
                continue
            return cleaned
        except (DeepSeekError, LLMError) as exc:
            if attempt == 1:
                raise InternalLinkSelectionError(str(exc)) from exc
