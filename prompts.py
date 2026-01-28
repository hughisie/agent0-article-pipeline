TRANSLATION_SYSTEM = (
    "You are a careful research assistant.\n"
    "You MUST respond only with valid JSON and no extra commentary.\n"
    "The translation must be clean natural English. Do NOT mix languages.\n"
    "If something is not known, return null. Do not speculate or invent details."
)

TRANSLATION_USER = (
    "You will receive JSON containing a news article. It may be in Spanish or another language.\n\n"
    "Your tasks:\n"
    "  1. Detect the language.\n"
    "  2. Translate the full article body (main_content_body) into English.\n"
    "  3. Summarise the article in English (4-6 sentences).\n"
    "  4. Infer whether the article is reporting on an ORIGINAL ARTIFACT such as:\n"
    "     - press release\n"
    "     - survey or barometer\n"
    "     - government announcement\n"
    "     - academic paper\n"
    "     - official report\n"
    "     - social media post\n"
    "     - court ruling\n"
    "     - other\n"
    "  5. Identify WHO likely produced the original artifact (organisation / institution).\n"
    "  6. Identify WHAT the artifact likely contains (data, results, statement, decision, etc.).\n"
    "  7. Extract key factual claims that appear to originate from that artifact (not just politicians' quotes).\n\n"
    "Return ONLY valid JSON in this exact shape:\n\n"
    "{\n"
    "  \"language_detected\": \"...\",\n"
    "  \"english_translation_full\": \"...\",\n"
    "  \"english_summary\": \"...\",\n"
    "  \"core_topic\": \"...\",\n"
    "  \"original_artifact_type\": \"...\",\n"
    "  \"probable_primary_publisher\": \"...\",\n"
    "  \"artifact_description\": \"...\",\n"
    "  \"key_claims\": [\"...\", \"...\"]\n"
    "}\n\n"
    "Here is the article JSON:\n"
    "<ARTICLE_JSON_HERE>"
)

PRIMARY_SYSTEM = (
    "You are an investigative research assistant specialising in tracing PRIMARY SOURCES.\n\n"
    "Be conservative:\n"
    "  - Prefer official / authoritative domains (.gov, .edu, official organisation domains).\n"
    "  - Prefer the earliest page where the underlying information first appears.\n"
    "  - Avoid blogs, generic news summaries, and aggregators.\n\n"
    "A PRIMARY SOURCE is the original place where the underlying information, data or announcement first appeared\n"
    "(e.g. an official government page, an official PDF report, a survey results page, or an original press release).\n\n"
    "If you cannot clearly identify a primary source, return null with low confidence.\n"
    "You MUST respond ONLY with valid JSON and no extra commentary."
)

PRIMARY_USER = (
    "We are trying to locate the PRIMARY SOURCE for a news article.\n\n"
    "Inputs:\n\n"
    "ARTICLE JSON:\n"
    "<ARTICLE_JSON_HERE>\n\n"
    "ANALYSIS FROM TRANSLATION STEP:\n"
    "<ANALYSIS_JSON_HERE>\n\n"
    "Using Google Search (grounded search), perform multiple targeted searches in the relevant languages (e.g. Spanish and English).\n\n"
    "Instructions:\n"
    "  - Generate search queries based on the article and the analysis (including names, institutions, barometer/survey names, dates, and city).\n"
    "  - Use search to find likely primary sources: official report pages, PDF reports, press releases, data portals, or institutional pages.\n"
    "  - Open each promising result long enough to verify whether it clearly contains the underlying data or official statement\n"
    "(e.g. survey results tables, methodology, fieldwork dates, sample size, or the exact announcement text).\n"
    "  - If the result is just a derivative news piece or commentary, do not treat it as primary.\n\n"
    "CRITICAL URL VALIDATION:\n"
    "  - ALWAYS verify the URL returns HTTP 200 (not 404, 403, or error page)\n"
    "  - ALWAYS verify the page content actually matches the article topic and date\n"
    "  - REJECT homepage URLs or association/about pages - only use specific document/statement/press release pages\n"
    "    ❌ BAD: https://www.telecogresca.com/associacio/ (homepage/about page)\n"
    "    ✅ GOOD: https://www.telecogresca.com/comunicats/2025/statement-festival-measures.html (specific statement)\n"
    "  - REJECT URLs that show 'article no longer available', 'unpublished', 'removed', or similar messages\n"
    "  - REJECT URLs with generic paths like /index, /home, /about, /associacio, /contact\n"
    "  - If you find multiple URLs with similar paths but different ID numbers (e.g., /notes-premsa/445831/ vs /notes-premsa/691002/), \n"
    "    CHECK EACH ONE and select the one that best matches the article date and content\n"
    "  - Prefer URLs with dates that match the article's timeframe (check publication dates in the page)\n"
    "  - If the page title/headline doesn't match the article topic, it's likely the wrong URL even if the slug looks similar\n"
    "  - Double-check that official announcement URLs (govern.cat, gencat.cat, etc.) are current and not outdated versions\n"
    "  - Verify the source actually contains the specific information mentioned in the article (names, numbers, dates)\n"
    "  - URL paths should contain indicators like: /comunicat/, /nota-premsa/, /press-release/, /statement/, /news/, /article-id/\n\n"
    "SOCIAL MEDIA SOURCES (Twitter/X, Facebook, Instagram):\n"
    "  - Social media posts often return 403 Forbidden or require authentication\n"
    "  - ALWAYS prefer official press releases or website statements over social media posts\n"
    "  - If you find a Twitter/X post, search for the same statement on the organization's official website\n"
    "  - Only use social media as primary source if:\n"
    "    1. You verify it loads without authentication (test the URL)\n"
    "    2. No official website alternative exists\n"
    "    3. It's the original source of breaking news\n"
    "  - For government/institutional statements, look for press sections on official websites (e.g., aena.es/en/press, gencat.cat/premsa)\n\n"
    "When choosing the primary source, prefer in this order:\n"
    "  1. Specific press release or statement page (NOT homepage/about page)\n"
    "  2. Official dataset or report containing data/methodology\n"
    "  3. Official PDF report or document\n"
    "  4. News article with original quotes/data\n"
    "  5. Verified, accessible social media post (only if above not available)\n"
    "  ❌ NEVER: Homepage, about/association pages, dead/unpublished links\n\n"
    "Return ONLY JSON in this structure:\n\n"
    "{\n"
    "  \"primary_source\": {\n"
    "    \"url\": \"string or null\",\n"
    "    \"title\": \"string or null\",\n"
    "    \"publisher_guess\": \"string or null\",\n"
    "    \"type_guess\": \"string or null\",\n"
    "    \"confidence\": 0.0\n"
    "  },\n"
    "  \"alternatives\": [\n"
    "    {\n"
    "      \"url\": \"string\",\n"
    "      \"title\": \"string\",\n"
    "      \"reason\": \"string\",\n"
    "      \"confidence\": 0.0\n"
    "    }\n"
    "  ],\n"
    "  \"reasoning_summary\": \"short explanation\"\n"
    "}\n\n"
    "Rules:\n"
    "  - If multiple official artifacts exist (e.g. landing page + PDF), choose the one that contains the data itself as primary, and list the others as alternatives.\n"
    "  - If unsure, set primary_source.url to null and use a low confidence value.\n"
    "  - Confidence must be between 0 and 1.\n\n"
    "The function should:\n"
    "  - Substitute the real JSON for <ARTICLE_JSON_HERE> and <ANALYSIS_JSON_HERE>.\n"
    "  - Call Gemini 2.5 Flash with search grounding enabled.\n"
    "  - Parse and return the JSON."
)


def resolve_prompt(config: dict | None, key: str, default: str) -> str:
    """
    Resolve a prompt value with the following priority:
    1. Config dict (passed explicitly)
    2. Active profile's custom prompt (from database)
    3. Default value
    """
    # First check config dict if provided
    if config:
        value = config.get(key)
        if value:
            return value

    # Then check active profile's custom prompts
    try:
        from agent0_gui.profile_manager import get_active_profile, get_profile_prompt
        profile = get_active_profile()
        if profile:
            custom_prompt = get_profile_prompt(profile["id"], key)
            if custom_prompt:
                return custom_prompt
    except ImportError:
        # If profile_manager not available (e.g., running outside GUI), skip
        pass
    except Exception:
        # If there's any error reading from database, fall back to default
        pass

    # Finally use default
    return default
