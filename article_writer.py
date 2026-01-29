import json
import re
import unicodedata

from llm_clients import GeminiClient, LLMError, parse_json_response
from prompts import resolve_prompt


# American to British English spelling conversions
AMERICAN_TO_BRITISH = {
    # -ize to -ise
    "organized": "organised",
    "recognized": "recognised",
    "emphasized": "emphasised",
    "realized": "realised",
    "specialized": "specialised",
    "characterized": "characterised",
    "prioritized": "prioritised",
    "maximized": "maximised",
    "minimized": "minimised",
    "authorized": "authorised",
    "legalized": "legalised",
    "finalized": "finalised",
    "analyzed": "analysed",
    "capitalized": "capitalised",
    "standardized": "standardised",
    "localized": "localised",
    "utilized": "utilised",
    "optimized": "optimised",
    "modernized": "modernised",
    "centralized": "centralised",
    "decentralized": "decentralised",
    "digitized": "digitised",
    "monetized": "monetised",
    "subsidized": "subsidised",
    "criticized": "criticised",
    "symbolized": "symbolised",
    "victimized": "victimised",
    "organization": "organisation",
    "organizations": "organisations",
    "specialization": "specialisation",
    "optimization": "optimisation",
    "modernization": "modernisation",
    "privatization": "privatisation",
    "centralization": "centralisation",
    # -or to -our
    "color": "colour",
    "colors": "colours",
    "favor": "favour",
    "favors": "favours",
    "labor": "labour",
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "harbor": "harbour",
    "honor": "honour",
    "honors": "honours",
    "neighbor": "neighbour",
    "neighbors": "neighbours",
    # -er to -re
    "center": "centre",
    "centers": "centres",
    "theater": "theatre",
    "theaters": "theatres",
    "liter": "litre",
    "liters": "litres",
    "meter": "metre",  # measurement unit only
    "meters": "metres",
    # -ense to -ence
    "defense": "defence",
    "offense": "offence",
    "license": "licence",  # noun form
    # Double consonants
    "traveled": "travelled",
    "traveling": "travelling",
    "traveler": "traveller",
    "travelers": "travellers",
    "canceled": "cancelled",
    "canceling": "cancelling",
    "modeled": "modelled",
    "modeling": "modelling",
    "labeled": "labelled",
    "labeling": "labelling",
    "leveled": "levelled",
    "leveling": "levelling",
    "fueled": "fuelled",
    "fueling": "fuelling",
    # Other
    "program": "programme",  # except for computer programs
    "programs": "programmes",
    "analog": "analogue",
    "catalog": "catalogue",
    "dialog": "dialogue",
    "gray": "grey",
    "aging": "ageing",
    "judgment": "judgement",
    "acknowledgment": "acknowledgement",
}


def convert_to_british_english(text: str) -> str:
    """Convert American English spellings to British English."""
    if not text:
        return text

    result = text

    for american, british in AMERICAN_TO_BRITISH.items():
        def replace_match(match):
            """Preserve the case of the original word."""
            word = match.group(0)
            if word[0].isupper():
                if word.isupper() and len(word) > 1:
                    # All caps: ORGANIZED -> ORGANISED
                    return british.upper()
                else:
                    # Title case: Organized -> Organised
                    return british.capitalize()
            else:
                # lowercase: organized -> organised
                return british

        # Use a custom replacement function to preserve case
        result = re.sub(
            r'\b' + re.escape(american) + r'\b',
            replace_match,
            result,
            flags=re.IGNORECASE
        )

    return result


def build_gemini_article_prompt(
    original_article: dict,
    analysis: dict,
    primary_source: dict,
    related_articles: dict | None = None,
    prompt_overrides: dict | None = None,
) -> dict:
    system_message = (
        "You are a professional news journalist writing clear, modern articles for intelligent but busy readers.\n"
        "You write in British English with clarity, flow, and readability as top priorities.\n"
        "Your writing is factual, concrete, and accessible—like something published in a major newspaper, not a policy report.\n"
        "You follow Yoast SEO best practices for focus keyphrase, meta title, meta description, headings and readability.\n"
        "You respond ONLY with valid JSON and no extra commentary.\n"
        "Do not fabricate facts. If a detail is unknown, leave it out."
    )

    original_json = json.dumps(_normalise_unicode(original_article), ensure_ascii=False, indent=2)
    analysis_json = json.dumps(_normalise_unicode(analysis), ensure_ascii=False, indent=2)
    primary_json = json.dumps(_normalise_unicode(primary_source), ensure_ascii=False, indent=2)

    user_message = (
        "You will receive three JSON objects:\n"
        "  1. The original scraped article metadata and raw body.\n"
        "  2. A translation and analysis JSON.\n"
        "  3. A primary source JSON describing the original official report or announcement.\n\n"
        "Your tasks:\n"
        "  1. Identify the most appropriate primary SEO keyphrase for this news story.\n"
        "  2. Write a meta title (max ~60 chars) including the keyphrase near the start.\n"
        "  3. Write a meta description (max ~145 chars), compelling and human, including the keyphrase once.\n"
        "  4. Generate a slug for WordPress (lowercase, hyphen separated).\n"
        "  5. Suggest 3-6 SEO-friendly tags.\n"
        "  6. Write a short excerpt (1-2 sentences) summarising the story.\n"
        "  7. Write a full WordPress-ready article using Gutenberg block markup:\n"
        "     - Use Gutenberg block comments (<!-- wp:... -->).\n"
        "     - Include exactly one H1 block for the title.\n"
        "     - Begin with at least two paragraph blocks before the first H2 block.\n"
        "     - Use H2 blocks for main sections and H3 blocks sparingly.\n"
        "     - Use paragraph blocks for body text and include links inside paragraphs.\n"
        "     - Minimum 300 words based on the primary source and key claims.\n"
        "     - Written in British English for intelligent but busy readers.\n"
        "     - Optimised for mobile readability.\n"
        "     - Based on facts only; do not speculate.\n"
        "     - Include at least one hyperlink to the primary source URL.\n"
        "     - Use the focus keyphrase in the first paragraph, at least one H2, and naturally throughout.\n\n"
        "CRITICAL EXTERNAL LINKING RULES:\n"
        "  - NEVER INVENT OR CONSTRUCT URLs - only use URLs that are explicitly provided in the input data\n"
        "  - If a URL is not provided in the article data, primary source data, or analysis, DO NOT CREATE ONE\n"
        "  - NEVER guess URL paths, filenames, or IDs - even if they seem logical\n"
        "    ❌ FORBIDDEN: Constructing 'https://lamoncloa.gob.es/.../160126-afiliacion-extranjeros.aspx' from context\n"
        "    ✓ CORRECT: Only link to the primary_source.url provided, or don't link at all\n"
        "  - NEVER include links with placeholder IDs like 'XXXXX' or '/status/XXXXX'\n"
        "  - NEVER link to generic homepages without a specific page:\n"
        "    ❌ FORBIDDEN: https://www.icao.int/\n"
        "    ❌ FORBIDDEN: https://www.example.com/\n"
        "    ✓ ALLOWED: https://www.icao.int/security/safeguarding/pages/default.aspx (specific page)\n"
        "  - If you mention an external organization but don't have a specific relevant URL, do NOT add a link\n"
        "  - Only add external links if ALL of these are true:\n"
        "    1. The URL was PROVIDED in the input data (not constructed by you)\n"
        "    2. The URL is complete and specific (not just a domain homepage)\n"
        "    3. The URL directly supports the specific claim being made\n"
        "  - When referencing government reports, ministry statements, or official data:\n"
        "    ✓ CORRECT: \"According to the Ministry of Inclusion, foreign workers now represent 14.1% of contributors.\"\n"
        "    ❌ WRONG: \"<a href='https://lamoncloa.gob.es/...[invented path]'>According to the Ministry</a>...\"\n"
        "  - When mentioning organizations for context, do NOT add generic homepage links:\n"
        "    ✓ CORRECT: \"...as outlined by international aviation security protocols.\"\n"
        "    ❌ WRONG: \"...from the <a href='https://www.icao.int/'>International Civil Aviation Organization</a>.\"\n"
        "  - If you cannot find a specific, verified URL in the provided data, it's better to have NO link than an invented link\n\n"
        "SOCIAL MEDIA LINKS (STRICT RULES):\n"
        "  - NEVER construct Twitter/X URLs with guessed status IDs\n"
        "    ❌ FORBIDDEN: https://x.com/salvadorilla/status/1748057288647704739 (if not in input data)\n"
        "    ❌ FORBIDDEN: https://twitter.com/username/status/[any ID you think might be right]\n"
        "  - Twitter/X status IDs are unique 18-19 digit numbers - you cannot guess them\n"
        "  - If the article mentions a tweet/post but doesn't provide the exact URL, do NOT link to it\n"
        "  - Same applies to Instagram, Facebook, LinkedIn - never construct social media URLs\n"
        "  - If you want to reference a social media post:\n"
        "    ✓ CORRECT: \"Illa posted on X announcing the meeting.\" (no link)\n"
        "    ❌ WRONG: \"Illa <a href='https://x.com/salvadorilla/status/[made-up-id]'>posted on X</a> announcing the meeting.\"\n"
        "  - ONLY link to social media if the EXACT URL is provided in the input data\n\n"
        "CRITICAL WRITING RULES (Modern British Journalism):\n\n"
        "1. OPENING SENTENCE:\n"
        "   - Start with a strong, concrete fact that states the key impact on people\n"
        "   - Example: \"One in three people using public transport in Barcelona now travels on a discounted or social ticket.\"\n"
        "   - NOT: \"Barcelona's transport system has undergone significant changes...\"\n\n"
        "2. PARAGRAPH STRUCTURE:\n"
        "   - One idea per paragraph\n"
        "   - Maximum 2-3 sentences per paragraph\n"
        "   - Short, punchy, easy to scan on mobile\n\n"
        "3. ACTIVE VOICE:\n"
        "   - Put institutions and people at the start of sentences\n"
        "   - Example: \"The government is using cheaper tickets to reduce car use.\"\n"
        "   - NOT: \"Fare policy is being used as a lever to reduce car use.\"\n\n"
        "4. SIMPLE LANGUAGE:\n"
        "   - Use plain English over abstract academic wording\n"
        "   - NEVER use: \"structural reconfiguration\", \"institutional message\", \"funding architecture\", \"lever\", \"ambition is to\"\n"
        "   - Turn concepts into actions: \"The council plans to...\" not \"The ambition is to...\"\n\n"
        "5. STATISTICS:\n"
        "   - State the number first, then explain what it means\n"
        "   - Example: \"33% of all passengers now use discounted fares. That shows subsidised travel is no longer marginal.\"\n\n"
        "6. SENTENCE LENGTH:\n"
        "   - If a sentence has more than one comma, split it\n"
        "   - Aim for natural, spoken rhythm\n"
        "   - Break up long, complex sentences\n\n"
        "7. EXPLAIN POLICY SIMPLY:\n"
        "   - Present funding or subsidies as if explaining to a commuter\n"
        "   - Example: \"The State pays 20% of the discount. The Generalitat covers the remaining 30%.\"\n\n"
        "8. SUBHEADINGS (H2/H3):\n"
        "   - Must answer real questions readers would ask\n"
        "   - Example: \"Who qualifies for these tickets?\", \"Who pays for the discounts?\", \"What's changing with ticket technology?\"\n"
        "   - NOT: \"Policy Implementation Framework\" or \"Strategic Overview\"\n\n"
        "9. TONE:\n"
        "   - Confident, journalistic, factual\n"
        "   - NO ceremonial or inflated language\n"
        "   - NO academic framing\n"
        "   - NEVER use: \"the objective is\", \"the ambition is\", \"this demonstrates that\"\n"
        "   - NEVER use: \"marks a significant milestone\", \"in an exciting development\"\n\n"
        "10. BRITISH ENGLISH SPELLING (MANDATORY):\n"
        "    - ALWAYS use British spelling, NEVER American:\n"
        "      ✓ organised, NOT organized\n"
        "      ✓ recognised, NOT recognized\n"
        "      ✓ emphasised, NOT emphasized\n"
        "      ✓ realised, NOT realized\n"
        "      ✓ specialised, NOT specialized\n"
        "      ✓ characterised, NOT characterized\n"
        "      ✓ prioritised, NOT prioritized\n"
        "      ✓ maximised, NOT maximized\n"
        "      ✓ minimised, NOT minimized\n"
        "      ✓ authorised, NOT authorized\n"
        "      ✓ legalised, NOT legalized\n"
        "      ✓ finalised, NOT finalized\n"
        "      ✓ analysed, NOT analyzed\n"
        "      ✓ capitalised, NOT capitalized\n"
        "      ✓ standardised, NOT standardized\n"
        "      ✓ localised, NOT localized\n"
        "      ✓ colour, NOT color\n"
        "      ✓ favour, NOT favor\n"
        "      ✓ labour, NOT labor\n"
        "      ✓ behaviour, NOT behavior\n"
        "      ✓ centre, NOT center\n"
        "      ✓ metre, NOT meter (measurement)\n"
        "      ✓ defence, NOT defense\n"
        "      ✓ offence, NOT offense\n"
        "      ✓ licence, NOT license (noun)\n"
        "      ✓ travelling, NOT traveling\n"
        "      ✓ cancelled, NOT canceled\n"
        "      ✓ modelling, NOT modeling\n"
        "      ✓ programme, NOT program (except for computer programs)\n"
        "    - If in doubt, prefer the -ise/-isation form over -ize/-ization\n\n"
        "11. BANNED PHRASES (NEVER USE THESE):\n"
        "    ❌ \"have cause for celebration\"\n"
        "    ❌ \"That debate has been building for months\"\n"
        "    ❌ \"excited the community\"\n"
        "    ❌ \"will be closely following\"\n"
        "    ❌ \"structural reconfiguration\"\n"
        "    ❌ \"institutional message\"\n"
        "    ❌ \"funding architecture\"\n"
        "    ❌ \"lever for change\"\n"
        "    ❌ \"the ambition is to\"\n"
        "    ❌ \"the objective is to\"\n"
        "    ❌ \"this demonstrates that\"\n\n"
        "12. CLOSING PARAGRAPH / CALL-TO-ACTION RULES:\n"
        "    - NEVER end with generic \"For more information, visit [organization] website\" linking to a homepage\n"
        "    - FORBIDDEN closing patterns:\n"
        "      ❌ \"For more information on Barcelona's cultural venues, visit the Barcelona City Council website.\" (links to https://www.barcelona.cat/)\n"
        "      ❌ \"Visit the official website for more details.\" (links to homepage)\n"
        "      ❌ \"More information is available at [organization].\" (links to homepage)\n"
        "    - ACCEPTABLE closing approaches (in order of preference):\n"
        "      1. End with a relevant fact, quote, or forward-looking statement about the story\n"
        "         ✓ \"The new measures will take effect from March 2026.\"\n"
        "         ✓ \"Officials said further details would be announced in the coming weeks.\"\n"
        "      2. If you have a SPECIFIC relevant link (not homepage), integrate it naturally:\n"
        "         ✓ \"Full survey results are available in the <a href='https://example.com/reports/2026/survey.pdf'>official report</a>.\"\n"
        "         ✓ \"The council has published the <a href='https://example.com/planning/2026/proposal'>detailed proposal</a> online.\"\n"
        "      3. Provide context without any link:\n"
        "         ✓ \"The Barcelona City Council maintains information on cultural venues and events.\"\n"
        "         ✓ \"Further updates will be published on the official website.\"\n"
        "    - NEVER add a closing paragraph just to include a link\n"
        "    - The article should feel complete without needing a generic \"visit website\" CTA\n\n"
        "FINAL CHECK:\n"
        "  - The article must be easily readable on a phone\n"
        "  - It must sound like something from The Guardian or BBC News, not a policy report\n"
        "  - Every sentence should pass the \"would you say this out loud?\" test\n"
        "  - The closing paragraph must NOT contain a generic homepage link\n\n"
        "Example format:\n"
        "<!-- wp:heading {\"level\":1} -->\n"
        "<h1>Title here</h1>\n"
        "<!-- /wp:heading -->\n\n"
        "<!-- wp:paragraph -->\n"
        "<p>Intro paragraph with keyphrase...</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:heading {\"level\":2} -->\n"
        "<h2>Section heading</h2>\n"
        "<!-- /wp:heading -->\n\n"
        "<!-- wp:paragraph -->\n"
        "<p>Body text...</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "Return ONLY valid JSON in this exact structure:\n\n"
        "{\n"
        "  \"meta_title\": \"...\",\n"
        "  \"meta_description\": \"...\",\n"
        "  \"primary_keyword\": \"...\",\n"
        "  \"slug\": \"...\",\n"
        "  \"tags\": [\"...\", \"...\"],\n"
        "  \"excerpt\": \"...\",\n"
        "  \"wp_block_content\": \"...\"\n"
        "}\n\n"
        "Here is the original article JSON:\n"
        "<ORIGINAL_ARTICLE_JSON_HERE>\n\n"
        "Here is the translation & analysis JSON:\n"
        "<ANALYSIS_JSON_HERE>\n\n"
        "Here is the primary source JSON:\n"
        "<PRIMARY_SOURCE_JSON_HERE>"
    )

    system_message = resolve_prompt(prompt_overrides, "PROMPT_ARTICLE_SYSTEM", system_message)
    user_message = resolve_prompt(prompt_overrides, "PROMPT_ARTICLE_USER", user_message)
    user_message = user_message.replace("<ORIGINAL_ARTICLE_JSON_HERE>", original_json)
    user_message = user_message.replace("<ANALYSIS_JSON_HERE>", analysis_json)
    user_message = user_message.replace("<PRIMARY_SOURCE_JSON_HERE>", primary_json)

    if related_articles is not None:
        related_json = json.dumps(_normalise_unicode(related_articles), ensure_ascii=False, indent=2)
        user_message += (
            "\n\nYou will also receive a JSON object describing some existing articles from this site that should be referenced in the new article when appropriate.\n"
            "For each entry, you will see: url, title, anchor_text, why_relevant, and suggested_insertion.\n\n"
            "Please:\n"
            "  - Weave up to 3 references into the article body in a natural way.\n"
            "  - Use standard HTML anchor tags for each hyperlink, e.g.:\n"
            "    <a href=\"URL\">anchor_text</a>\n"
            "  - Place one link in the intro or early body if possible.\n"
            "  - Do not over-link: at most one link per related article.\n\n"
            "CRITICAL LINKING REQUIREMENTS:\n"
            "  - Each related article link MUST be introduced with a UNIQUE phrase or sentence structure.\n"
            "  - NEVER repeat the same linking pattern or sentence structure.\n"
            "  - Vary your linking style for each reference:\n"
            "    * First link: Natural contextual reference (e.g., \"The city previously addressed similar concerns about...\")\n"
            "    * Second link: Background reference (e.g., \"This follows earlier action on...\")\n"
            "    * Third link: Continuation reference (e.g., \"The issue connects to broader questions about...\")\n"
            "  - Use different sentence structures and vocabulary for each link.\n"
            "  - Avoid formulaic patterns like \"we covered it in...\" or \"as we reported in...\"\n"
            "  - Make each link introduction flow naturally from the surrounding paragraph's topic.\n"
            "  - If you cannot introduce a link naturally and uniquely, skip it rather than force it.\n\n"
            "EXAMPLES OF LINKING VARIETY:\n"
            "  ❌ BAD (repetitive - DO NOT DO THIS):\n"
            "    \"That debate has been building for months — we covered it in streamlining municipal bureaucracy.\"\n"
            "    \"That debate has been building for months — we covered it in scrutiny of public service operations.\"\n\n"
            "  ✅ GOOD (varied - DO THIS):\n"
            "    \"The city previously addressed similar concerns when streamlining municipal bureaucracy.\"\n"
            "    \"This follows earlier scrutiny of public service operations, which raised questions about oversight.\"\n"
            "    \"Related questions emerged during recent discussions about transparency requirements.\"\n\n"
            "RELATED ARTICLES JSON:\n"
            f"{related_json}"
        )

    return {"system_message": system_message, "user_message": user_message}


def _normalise_unicode(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalise_unicode(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalise_unicode(val) for key, val in value.items()}
    return value


def _ensure_single_h1_block(content: str, title: str | None) -> str:
    if not content:
        return content
    h1_block = "<!-- wp:heading {\"level\":1} -->"
    h1_tag = "<h1>"
    h1_close = "</h1>"

    if h1_block not in content and h1_tag not in content:
        safe_title = title or ""
        h1_html = (
            f"{h1_block}\n<h1>{safe_title}</h1>\n<!-- /wp:heading -->\n\n"
        )
        return h1_html + content

    # Convert any additional H1 blocks after the first to H2 blocks
    parts = content.split(h1_block)
    if len(parts) > 2:
        rebuilt = [parts[0], h1_block + parts[1]]
        for fragment in parts[2:]:
            fragment = fragment.replace(h1_tag, "<h2>").replace(h1_close, "</h2>")
            fragment = fragment.replace("\"level\":1", "\"level\":2")
            rebuilt.append("<!-- wp:heading {\"level\":2} -->" + fragment)
        content = "".join(rebuilt)

    # If multiple <h1> tags exist, downgrade extras
    def _downgrade(match):
        return "<h2>"

    h1_matches = list(re.finditer(r"<h1>", content, flags=re.IGNORECASE))
    if len(h1_matches) > 1:
        first = h1_matches[0].start()
        content = content[: first + 4] + content[first + 4 :]
        content = re.sub(r"<h1>", _downgrade, content, flags=re.IGNORECASE, count=len(h1_matches) - 1)
        content = re.sub(r"</h1>", "</h2>", content, flags=re.IGNORECASE)

    return content


def _ensure_intro_paragraphs(content: str, primary_keyword: str | None, excerpt: str | None) -> str:
    if not content:
        return content
    h2_block = "<!-- wp:heading {\"level\":2} -->"
    idx = content.find(h2_block)
    if idx == -1:
        return content

    before = content[:idx]
    paragraph_count = before.count("<!-- wp:paragraph -->")
    if paragraph_count >= 2:
        return content

    intro_one = excerpt or "The latest figures highlight a notable shift in demand across the sector."
    if primary_keyword:
        intro_two = (
            f"This update adds fresh context to the story of {primary_keyword}, as the market adjusts to new pressures."
        )
    else:
        intro_two = "This update adds fresh context to the story, as the market adjusts to new pressures."

    paragraph_block = (
        "<!-- wp:paragraph -->\n"
        "<p>{text}</p>\n"
        "<!-- /wp:paragraph -->\n\n"
    )

    insert = "".join(
        [
            paragraph_block.format(text=intro_one),
            paragraph_block.format(text=intro_two),
        ]
    )

    return before + insert + content[idx:]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _validate_article_payload(payload: dict) -> dict:
    required_keys = [
        "meta_title",
        "meta_description",
        "primary_keyword",
        "slug",
        "tags",
        "excerpt",
    ]
    for key in required_keys:
        if key not in payload:
            raise LLMError(f"Missing key in article payload: {key}")

    if "wp_block_content" not in payload and "wp_html_content" in payload:
        payload["wp_block_content"] = payload["wp_html_content"]

    if "wp_block_content" not in payload:
        raise LLMError("Missing 'wp_block_content' in article payload")

    if not isinstance(payload.get("tags"), list):
        raise LLMError("Expected 'tags' to be a list")

    return payload


def generate_wp_article(
    original_article: dict,
    analysis: dict,
    primary_source: dict,
    related_articles: dict | None = None,
    model_name: str = "gemini-2.0-flash-exp",
    api_keys: dict | None = None,
) -> dict:
    if not api_keys or not api_keys.get("GEMINI_API_KEY"):
        raise LLMError("GEMINI_API_KEY is required for article generation")

    prompt = build_gemini_article_prompt(
        original_article,
        analysis,
        primary_source,
        related_articles,
        prompt_overrides=api_keys,
    )
    client = GeminiClient(api_key=api_keys["GEMINI_API_KEY"], model=model_name)

    for attempt in range(2):
        raw = client.generate(prompt["system_message"], prompt["user_message"], timeout=240)
        try:
            payload = _normalise_unicode(parse_json_response(raw))
            payload = _validate_article_payload(payload)
            content = payload.get("wp_block_content", "")
            content = _ensure_single_h1_block(content, payload.get("meta_title"))
            content = _ensure_intro_paragraphs(content, payload.get("primary_keyword"), payload.get("excerpt"))
            # Convert any American spellings to British English
            content = convert_to_british_english(content)
            payload["wp_block_content"] = content
            # Also convert meta fields
            if payload.get("meta_title"):
                payload["meta_title"] = convert_to_british_english(payload["meta_title"])
            if payload.get("meta_description"):
                payload["meta_description"] = convert_to_british_english(payload["meta_description"])
            if payload.get("excerpt"):
                payload["excerpt"] = convert_to_british_english(payload["excerpt"])
            return {
                **payload,
                "llm_debug_context": {
                    "used_model": model_name,
                    "prompt_tokens_estimate": _estimate_tokens(
                        prompt["system_message"] + prompt["user_message"]
                    ),
                },
            }
        except LLMError:
            if attempt == 1:
                raise
