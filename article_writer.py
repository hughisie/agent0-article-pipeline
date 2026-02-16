import json
import re
import unicodedata

from llm_clients import GeminiClient, LLMClient, LLMError, ContentModerationError, parse_json_response
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
    related_articles: dict | None = None,  # Now ignored - handled in Phase 2
    prompt_overrides: dict | None = None,
) -> dict:
    """
    Build the article generation prompt.
    
    PHASE 1: Pure content generation - NO internal links.
    Internal links are added in Phase 2 by link_integrator.py.
    """
    system_message = (
        "You are a senior journalist at The Guardian, writing for an English-speaking audience in Barcelona/Catalonia.\n"
        "Your writing is engaging, conversational, and reads like quality British journalism.\n"
        "You respond ONLY with valid JSON and no extra commentary.\n"
        "Do not fabricate facts. If a detail is unknown, leave it out.\n\n"
        "🔴 YOAST SEO REQUIREMENTS (MANDATORY — EVERY CHECK MUST SCORE GREEN):\n"
        "  1. KEYPHRASE: Maximum 4 content words (e.g., 'Barcelona metro changes' NOT 'Barcelona metro station name changes')\n"
        "  2. SEO TITLE: Keyphrase MUST appear at the VERY BEGINNING of the meta title (first words)\n"
        "     - Max 55 characters total (to avoid truncation in search results)\n"
        "     - Example: 'Barcelona Metro Changes: Five Stations Get New Names'\n"
        "  3. META DESCRIPTION: 120-150 characters (NEVER exceed 155). Include keyphrase once.\n"
        "  4. FIRST PARAGRAPH: The exact keyphrase MUST appear in the first paragraph (introduction). This is MANDATORY.\n"
        "  5. KEYPHRASE DENSITY: Use the exact keyphrase 4-8 times throughout the article (0.5-2.5%)\n"
        "  6. SUBHEADINGS: At least one H2 must contain the keyphrase or a close synonym\n"
        "  7. SLUG: Must contain the keyphrase words\n"
        "  8. MINIMUM 400 WORDS of article body text (excluding HTML markup)\n"
        "  9. Paragraphs under 150 words each\n"
        "  10. Sentences under 20 words on average\n"
        "  11. Use transition words in >35% of sentences (however, therefore, additionally, moreover, meanwhile, furthermore, as a result, consequently)\n"
        "  12. Use subheadings (H2) every 250-300 words\n"
        "  13. Passive voice in fewer than 10% of sentences\n\n"
        "LINKING RULES:\n"
        "  - MUST include ONE link to the primary source URL if provided in the PRIMARY SOURCE JSON\n"
        "  - SHOULD include 1-2 links to KEY ORGANIZATIONS mentioned in the article (city councils, cooperatives, etc.)\n"
        "  - DO NOT add internal links to other news articles - these will be added separately\n"
        "  - DO NOT link to Wikipedia or generic news sites\n"
        "  - NEVER add generic 'For more information' sentences like:\n"
        "    ❌ 'For more information, visit the WHO website'\n"
        "    ❌ 'You can learn more about X from the British Museum'\n"
        "    ❌ 'For broader context, see this European Central Bank report'\n"
        "  - NEVER add links to generic authoritative sources (WHO, World Bank, ECB, British Museum, etc.) unless directly cited in the original\n"
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
        "  1. Identify the most appropriate primary SEO keyphrase (MAX 4 content words, e.g., 'Barcelona crime rates').\n"
        "  2. Write a meta title (max 55 chars) with keyphrase as the FIRST WORDS.\n"
        "  3. Write a meta description (120-150 chars, NEVER over 155), including the keyphrase once.\n"
        "  4. Generate a slug for WordPress (lowercase, hyphen separated).\n"
        "  5. Suggest 3-6 SEO-friendly tags.\n"
        "  6. Write a short excerpt (1-2 sentences) summarising the story.\n"
        "  7. Write a full WordPress-ready article using Gutenberg block markup:\n"
        "     - Use Gutenberg block comments (<!-- wp:... -->).\n"
        "     - Include exactly one H1 block for the title.\n"
        "     - Begin with at least two paragraph blocks before the first H2 block.\n"
        "     - Use H2 blocks for main sections and H3 blocks sparingly.\n"
        "     - Use paragraph blocks for body text and include links inside paragraphs.\n"
        "     - MINIMUM 400 WORDS of body text (this is a hard requirement, articles under 300 words fail).\n"
        "     - Written in British English for intelligent but busy readers.\n"
        "     - Optimised for mobile readability.\n"
        "     - Based on facts only; do not speculate.\n"
        "     - Use the focus keyphrase in the first paragraph, at least one H2, and naturally throughout.\n\n"
        "🔴 MANDATORY PRIMARY SOURCE LINK REQUIREMENT:\n"
        "  - You MUST include at least ONE hyperlink to the PRIMARY SOURCE URL\n"
        "  - The primary source URL is provided in the primary_source.url field of the PRIMARY SOURCE JSON\n"
        "  - This is the ACTUAL SOURCE of the article's information - link to it naturally when citing data or facts\n"
        "  - Example integrations:\n"
        "    ✓ \"According to the <a href='[primary_source.url]'>official report</a>, the numbers show...\"\n"
        "    ✓ \"The <a href='[primary_source.url]'>government announcement</a> confirmed that...\"\n"
        "    ✓ \"Data from the <a href='[primary_source.url]'>survey results</a> revealed...\"\n"
        "    ✓ \"The <a href='[primary_source.url]'>company's blog post</a> described the new features...\"\n"
        "  - Place this link early in the article when first introducing key data or claims\n"
        "  - The primary source can be a government press release OR a company's own blog/press page\n"
        "  - If primary_source.url is null or empty, then DON'T add any external links (better no link than wrong link)\n\n"
        "🔵 ORGANIZATION/BUSINESS/INSTITUTION LINKING (IMPORTANT):\n"
        "  - When you mention a KEY ORGANIZATION, BUSINESS, or INSTITUTION by name, you SHOULD link to their official website\n"
        "  - This applies to: city councils, cooperatives, government bodies, companies, businesses, fitness clubs, NGOs, universities\n"
        "  - Use their OFFICIAL HOMEPAGE URL (this is an exception to the 'no homepage' rule for organizations)\n"
        "  - Examples of good organization/business links:\n"
        "    ✓ \"The <a href='https://www.elprat.cat/' target='_blank' rel='noopener'>El Prat de Llobregat City Council</a> announced...\"\n"
        "    ✓ \"...led by the <a href='https://www.cov.cat/' target='_blank' rel='noopener'>Cooperativa Obrera de Viviendas</a>.\"\n"
        "    ✓ \"The <a href='https://ajuntament.barcelona.cat/' target='_blank' rel='noopener'>Barcelona City Council</a> confirmed...\"\n"
        "    ✓ \"The <a href='https://www.dir.cat/' target='_blank' rel='noopener'>DiR fitness chain</a> opened its new club...\"\n"
        "  - For Catalan/Spanish organizations and businesses, search for their official .cat, .com, or .es domain\n"
        "  - Common patterns:\n"
        "    - City councils: ajuntament.[city].cat or www.[city].cat\n"
        "    - Cooperatives: www.[name].cat or www.[name].coop\n"
        "    - Government: gencat.cat, govern.cat, lamoncloa.gob.es\n"
        "    - Businesses: www.[name].cat, www.[name].com, www.[name].es\n"
        "  - Link at FIRST MENTION of the organization in the article\n"
        "  - Maximum 2-3 organization links per article (don't overdo it)\n"
        "  - If you're unsure of the exact URL, you may use well-known official domains\n\n"
        "LINK SUMMARY (WHAT TO INCLUDE):\n"
        "  1. PRIMARY SOURCE: Link to primary_source.url from the JSON (MANDATORY if URL exists)\n"
        "  2. ORGANIZATIONS: Link 1-2 key organizations to their official .cat/.es/.org homepages\n"
        "  3. NO OTHER LINKS: No Wikipedia, no news sites, no invented URLs\n\n"
        "FORBIDDEN LINKS:\n"
        "  - NEVER invent URLs or guess paths (e.g., don't construct lamoncloa.gob.es/... paths)\n"
        "  - NEVER link to Twitter/X with guessed status IDs\n"
        "  - NEVER link to Wikipedia or other news sites\n"
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
        "3. ACTIVE VOICE (TARGET: LESS THAN 10% PASSIVE SENTENCES):\n"
        "   - Put institutions and people at the start of sentences\n"
        "   - Rewrite EVERY passive sentence to active before finishing\n"
        "   - Example: \"The government is using cheaper tickets to reduce car use.\"\n"
        "   - NOT: \"Fare policy is being used as a lever to reduce car use.\"\n"
        "   - Example: \"Bombers rescued three people from the building.\"\n"
        "   - NOT: \"Three people were rescued from the building by Bombers.\"\n"
        "   - Example: \"The council approved the plan on Tuesday.\"\n"
        "   - NOT: \"The plan was approved by the council on Tuesday.\"\n\n"
        "4. SIMPLE LANGUAGE:\n"
        "   - Use plain English over abstract academic wording\n"
        "   - NEVER use: \"structural reconfiguration\", \"institutional message\", \"funding architecture\", \"lever\", \"ambition is to\"\n"
        "   - Turn concepts into actions: \"The council plans to...\" not \"The ambition is to...\"\n\n"
        "5. STATISTICS:\n"
        "   - State the number first, then explain what it means\n"
        "   - Example: \"33% of all passengers now use discounted fares. That shows subsidised travel is no longer marginal.\"\n\n"
        "6. SENTENCE LENGTH AND VARIETY:\n"
        "   - If a sentence has more than one comma, split it\n"
        "   - Aim for natural, spoken rhythm\n"
        "   - Break up long, complex sentences\n"
        "   - DELIBERATELY vary sentence length: mix short punchy sentences (5-8 words) with longer ones (15-20 words)\n"
        "   - Start sentences with different parts of speech — avoid the 'The X...' pattern repeating\n"
        "   - Use contractions naturally: it's, don't, that's, won't, they're, hasn't\n"
        "   - Include occasional rhetorical questions to engage the reader\n\n"
        "6b. TRANSITION WORDS (TARGET: AT LEAST 40% OF SENTENCES):\n"
        "   - Use transition words frequently and naturally throughout the article\n"
        "   - Good transitions: however, meanwhile, as a result, in practice, on the ground,\n"
        "     at the same time, in response, separately, beyond that, notably, still,\n"
        "     in fact, for now, so far, yet, even so, on top of that\n"
        "   - Place transitions at the START of sentences, not buried in the middle\n"
        "   - Every paragraph should have at least one sentence with a transition word\n\n"
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
        "10. PUNCTUATION RULES (STRICTLY ENFORCED):\n"
        "    - ABSOLUTELY FORBIDDEN: em dashes (\u2014) and en dashes (\u2013)\n"
        "    - If you would use an em dash, rewrite using a comma, full stop, or parentheses instead\n"
        "    - Example: \"The project, which started in 2024, is now complete.\" NOT \"The project \u2014 which started in 2024 \u2014 is now complete.\"\n"
        "    - Use hyphens (-) ONLY for compound words (e.g., well-known, long-term)\n"
        "    - Use commas, full stops, and semicolons for sentence structure\n"
        "    - Use parentheses ( ) for asides if needed\n\n"
        "10b. FORMATTING RULES (STRICT):\n"
        "    - NEVER use <strong> or <b> bold tags in the article body\n"
        "    - NEVER use bold for emphasis, key terms, names, or statistics\n"
        "    - The ONLY exception is the H1 title and H2/H3 subheadings (which are already bold by default)\n"
        "    - Professional news articles (Guardian, BBC) do not bold random phrases\n"
        "    - Let the writing speak for itself without typographic emphasis\n\n"
        "11. BRITISH ENGLISH SPELLING (MANDATORY):\n"
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
        "    ❌ \"this demonstrates that\"\n"
        "    ❌ \"For more information on\" (NEVER start closing sentences this way)\n"
        "    ❌ \"For further reading\" (ABSOLUTELY BANNED - NEVER USE)\n"
        "    ❌ \"consider the [X] website\" (BANNED - no generic website suggestions)\n"
        "    ❌ \"visit [organization]'s coverage\" (BANNED - no vague link suggestions)\n\n"
        "12. CLOSING PARAGRAPH / CALL-TO-ACTION RULES (STRICT - NEVER VIOLATE):\n"
        "    - ABSOLUTELY FORBIDDEN: Generic \"For more information\" patterns with or without links\n"
        "    - FORBIDDEN PATTERNS (NEVER USE THESE):\n"
        "      ❌ \"For more information on [topic], you can read [organization]'s coverage...\" (NO LINK)\n"
        "      ❌ \"For more information on [topic], visit [organization].\" (https://example.com/)\n"
        "      ❌ \"For more information on transport disruptions, you can read the BBC's coverage of European transport news.\" (No link)\n"
        "      ❌ \"For more information on transport policy, visit the UK Government's transport department.\" (https://www.gov.uk/transport)\n"
        "      ❌ \"Visit the official website for more details.\" (links to homepage)\n"
        "      ❌ \"More information is available at [organization].\" (links to homepage)\n"
        "      ❌ \"Read more about [topic] at [organization].\" (any pattern)\n"
        "    - ABSOLUTELY BANNED: Any closing sentence starting with \"For more information\"\n"
        "    - ABSOLUTELY BANNED: Generic organization mentions with suggested links you don't have\n"
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

    # Inject additional_context if provided (URL-to-article or user-specified focus)
    additional_context = original_article.get("additional_context")
    if additional_context:
        user_message += (
            f"\n\nADDITIONAL CONTEXT FROM USER:\n"
            f"{additional_context}\n"
            f"Use this context to guide your article focus and angle."
        )

    # NOTE: related_articles is now ignored in Phase 1.
    # Internal links are added in Phase 2 by link_integrator.py after the article is generated.
    # This separation ensures the LLM focuses 100% on content quality first.

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


def _remove_em_dashes(text: str) -> str:
    """Replace em dashes with hyphens or commas as appropriate."""
    if not text:
        return text
    # Replace em dash with comma for lists/asides
    text = re.sub(r'\s+—\s+', ', ', text)
    # Replace em dash without spaces with hyphen
    text = re.sub(r'—', '-', text)
    return text


def _strip_generic_link_patterns(content: str) -> str:
    """Remove ALL generic link patterns including 'For further reading', 'For more information', etc."""
    if not content:
        return content
    
    # Patterns to completely remove (paragraph blocks with generic patterns)
    generic_patterns = [
        # "For more information" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?For more information[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?For more information[^<]*?</p>',
        
        # "For further reading" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?For further reading[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?For further reading[^<]*?</p>',
        
        # "For authoritative guidance" patterns (UK HSE style)
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?For authoritative guidance[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?For authoritative guidance[^<]*?</p>',
        
        # "refer to the" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?refer to the[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?refer to the[^<]*?</p>',
        
        # "Visit the X website" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?Visit the[^<]*?website[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?Visit the[^<]*?website[^<]*?</p>',
        
        # "consider the X website" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?consider the[^<]*?website[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?consider the[^<]*?website[^<]*?</p>',
        
        # Generic "Read more" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?Read more about[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?Read more about[^<]*?</p>',
        
        # "More information is available" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?More information is available[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?More information is available[^<]*?</p>',
        
        # Patterns with "(No link)" text
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?\(No link\)[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?\(No link\)[^<]*?</p>',
        
        # Patterns mentioning specific sites without actual links
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?(?:ArchDaily|Guardian|BBC|Reuters)[^<]*?coverage[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?(?:ArchDaily|Guardian|BBC|Reuters)[^<]*?coverage[^<]*?</p>',
        
        # "official X website" patterns
        r'<!--\s*wp:paragraph\s*-->\s*<p>[^<]*?official[^<]*?website[^<]*?</p>\s*<!--\s*/wp:paragraph\s*-->',
        r'<p>[^<]*?official[^<]*?website[^<]*?</p>',
        
        # "For more information on X, visit Y" patterns (without actual links)
        r'For more information on[^.]+,\s*visit[^.]+\.',
        r'For more information,\s*visit[^.]+\.',
    ]
    
    for pattern in generic_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up multiple blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    return content.strip()


def _strip_bold_formatting(content: str) -> str:
    """Remove all bold formatting (<strong>, <b>) from article body paragraphs.
    
    Professional news articles don't bold random phrases. Headings are already bold by default.
    """
    if not content:
        return content
    # Remove <strong>...</strong> tags, keeping inner content
    content = re.sub(r'<strong>(.*?)</strong>', r'\1', content, flags=re.DOTALL)
    # Remove <b>...</b> tags, keeping inner content
    content = re.sub(r'<b>(.*?)</b>', r'\1', content, flags=re.DOTALL)
    return content


def _strip_irrelevant_external_links(content: str) -> str:
    """Remove links to non-Spanish/Catalan sources that are irrelevant for Barcelona news."""
    if not content:
        return content
    
    # Domains that should NEVER appear in Barcelona/Catalonia news articles
    forbidden_domains = [
        r'hse\.gov\.uk',           # UK Health and Safety Executive
        r'gov\.uk',                # UK Government
        r'cdc\.gov',               # US CDC
        r'epa\.gov',               # US EPA
        r'fda\.gov',               # US FDA
        r'\.gov(?!\.es)',          # Any .gov that's not Spanish (.gov.es)
        r'nhs\.uk',                # UK NHS
        r'canada\.ca',             # Canadian government
        r'\.gov\.au',              # Australian government
    ]
    
    for domain in forbidden_domains:
        # Remove entire anchor tags with forbidden domains
        pattern = rf'<a\s+[^>]*href=["\'][^"\']*{domain}[^"\']*["\'][^>]*>([^<]*)</a>'
        content = re.sub(pattern, r'\1', content, flags=re.IGNORECASE)
    
    return content


def _strip_dangling_links(content: str) -> str:
    """Remove links that are just appended at the end of paragraphs without integration."""
    if not content:
        return content
    
    # Pattern: sentence ending with period, then a standalone link phrase ending with period
    # e.g., "...solar radiation exposure. <a href="...">Catalan exports to India</a>."
    # This catches: ". <a ...>text</a>." where the link is a dangling phrase
    dangling_pattern = r'\.\s*<a\s+href=["\'][^"\']+["\'][^>]*>([^<]{3,50})</a>\s*\.'
    
    def check_dangling(match):
        link_text = match.group(1).strip()
        # If the link text is a short phrase (likely a title), it's probably dangling
        # Real integrated links would have surrounding sentence context
        words = link_text.split()
        if len(words) <= 6:  # Short phrases are likely dangling
            return '.'  # Remove the dangling link, keep the period
        return match.group(0)  # Keep longer, likely integrated links
    
    content = re.sub(dangling_pattern, check_dangling, content)
    
    return content


def _strip_repetitive_link_sentences(content: str) -> str:
    """Remove repetitive link insertion patterns that break article flow."""
    if not content:
        return content
    
    # Patterns that are repetitive and should be removed
    repetitive_patterns = [
        # "The city previously addressed" - ALL VARIANTS (THE MAIN OFFENDER)
        r'The city previously addressed[^.]*\.',
        r'[A-Z][^.]*the city previously addressed[^.]*\.',
        
        # "Related questions emerged during discussions about X"
        r'Related questions emerged during discussions about[^.]*\.',
        
        # "The wider context is explained in our earlier piece on X"
        r'The wider context is explained in our earlier piece on[^.]*\.',
        
        # "This follows earlier action on X"
        r'This follows earlier action on\s*<a[^>]*>[^<]*</a>\.',
    ]
    
    for pattern in repetitive_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)
    
    # Clean up any double spaces or orphaned punctuation
    content = re.sub(r'\s+\.', '.', content)
    content = re.sub(r'\s{2,}', ' ', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    return content


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
    model_name: str = "gemini-exp-1206",
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

    # Use direct GeminiClient for specific model selection with Claude failover
    # This allows fine-grained model control while still supporting failover
    client = GeminiClient(api_key=api_keys["GEMINI_API_KEY"], model=model_name)

    for attempt in range(2):
        try:
            raw = client.generate(prompt["system_message"], prompt["user_message"], timeout=240)
        except ContentModerationError as e:
            # Content blocked - failover to Claude if available
            if "ANTHROPIC_API_KEY" in api_keys:
                print(f"\n⚠️  Gemini blocked content: {str(e)[:100]}")
                print(f"🔄 Failing over to Claude Sonnet 4.5 for sensitive content...")
                from llm_clients import AnthropicClient
                claude_client = AnthropicClient(api_key=api_keys["ANTHROPIC_API_KEY"])
                raw = claude_client.generate(prompt["system_message"], prompt["user_message"])
                print(f"✓ Claude successfully generated article")
            else:
                # No failover available
                raise
        try:
            payload = _normalise_unicode(parse_json_response(raw))
            payload = _validate_article_payload(payload)
            content = payload.get("wp_block_content", "")
            content = _ensure_single_h1_block(content, payload.get("meta_title"))
            content = _ensure_intro_paragraphs(content, payload.get("primary_keyword"), payload.get("excerpt"))
            # Remove em dashes
            content = _remove_em_dashes(content)
            # Strip bold formatting from article body
            content = _strip_bold_formatting(content)
            # Strip generic link patterns
            content = _strip_generic_link_patterns(content)
            # Remove irrelevant external links (UK/US gov sites for Barcelona news)
            content = _strip_irrelevant_external_links(content)
            # Remove repetitive link sentences like "The city previously addressed..."
            content = _strip_repetitive_link_sentences(content)
            # Remove dangling links that were just appended at end of paragraphs
            content = _strip_dangling_links(content)
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
