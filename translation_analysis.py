import json
from typing import Literal

from file_loader import Article
from llm_clients import LLMClient, parse_json_response, LLMError
from prompts import TRANSLATION_SYSTEM, TRANSLATION_USER, resolve_prompt


ModelChoice = Literal["gemini-2.5-pro", "deepseek"]


def translate_and_analyse_article(article: Article, model_choice: ModelChoice, api_keys: dict) -> dict:
    article_json = json.dumps(article.to_dict(), ensure_ascii=True, indent=2)
    system_prompt = resolve_prompt(api_keys, "PROMPT_TRANSLATION_SYSTEM", TRANSLATION_SYSTEM)
    user_template = resolve_prompt(api_keys, "PROMPT_TRANSLATION_USER", TRANSLATION_USER)
    user_prompt = user_template.replace("<ARTICLE_JSON_HERE>", article_json)

    client = LLMClient(model_choice=model_choice, api_keys=api_keys)

    for attempt in range(2):
        raw = client.generate(system_prompt, user_prompt)

        # Debug logging for empty responses
        if not raw or not raw.strip():
            print(f"WARNING: LLM returned empty response on attempt {attempt + 1}")
            if attempt == 1:
                raise LLMError("LLM returned empty response after 2 attempts")
            continue

        try:
            return parse_json_response(raw)
        except LLMError as e:
            print(f"WARNING: JSON parse error on attempt {attempt + 1}: {e}")
            print(f"Raw response preview: {raw[:500]}...")
            if attempt == 1:
                raise
