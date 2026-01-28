import json
import re
from urllib.parse import urlparse

from file_loader import Article
from llm_clients import GeminiSearchClient, LLMError, parse_json_response
from prompts import PRIMARY_SYSTEM, PRIMARY_USER, resolve_prompt


def _safe_text(value: str | None) -> str:
    return value.strip() if value else ""


def _extract_key_entities(title: str, analysis: dict) -> dict:
    """Extract key entities like dates, numbers, locations, and organizations from title and analysis."""
    entities = {
        "dates": [],
        "locations": [],
        "numbers": [],
        "organizations": []
    }
    
    # Extract year/dates from title
    date_patterns = [r'\b(20\d{2})\b', r'\b(19\d{2})\b', r'\b(gener|febrer|març|abril|maig|juny|juliol|agost|setembre|octubre|novembre|desembre)\s+(20\d{2})\b']
    for pattern in date_patterns:
        matches = re.findall(pattern, title.lower())
        if matches:
            entities["dates"].extend(matches if isinstance(matches, list) else [matches])
    
    # Extract percentages and numbers
    number_patterns = [r'(\d+[.,]?\d*)%', r'(\d+[.,]?\d*)\s*(milions?|millions?|milers?|thousands?)']
    for pattern in number_patterns:
        entities["numbers"].extend(re.findall(pattern, title.lower()))
    
    # Common Catalan/Spanish locations
    location_keywords = ['barcelona', 'catalunya', 'catalonia', 'generalitat', 'badalona', 'tarragona', 'lleida', 'girona']
    for loc in location_keywords:
        if loc in title.lower():
            entities["locations"].append(loc)
    
    return entities


def _get_domain_patterns(publisher: str, artifact_type: str) -> list[str]:
    """Get domain-specific URL patterns for known publishers."""
    patterns = []
    publisher_lower = publisher.lower() if publisher else ""
    
    # Catalan government
    if any(k in publisher_lower for k in ['generalitat', 'govern', 'gencat']):
        patterns.extend([
            'site:govern.cat/ca/noticies',
            'site:govern.cat/ca/comunicats',
            'site:gencat.cat/ca/actualitat',
            'site:web.gencat.cat/ca/actualitat'
        ])
    
    # Spanish government
    if any(k in publisher_lower for k in ['gobierno', 'ministerio', 'administración']):
        patterns.extend([
            'site:lamoncloa.gob.es/serviciosdeprensa',
            'site:*.gob.es/prensa'
        ])
    
    # Municipal governments
    if any(k in publisher_lower for k in ['ajuntament', 'ayuntamiento', 'badalona', 'barcelona']):
        patterns.extend([
            'site:ajuntament.barcelona.cat/premsa',
            'site:badalona.cat/ca/noticies'
        ])
    
    # Academic/research
    if artifact_type and 'survey' in artifact_type.lower() or 'barometer' in artifact_type.lower():
        patterns.extend([
            'site:*.edu',
            'site:ceo.gencat.cat',
            'filetype:pdf'
        ])
    
    return patterns


def _build_queries(article: Article, analysis: dict) -> list[str]:
    queries = []
    title = _safe_text(article.title) or _safe_text(article.original_title)
    publisher = _safe_text(analysis.get("probable_primary_publisher"))
    artifact_type = _safe_text(analysis.get("original_artifact_type"))
    language = _safe_text(analysis.get("language_detected")).lower()
    
    # Extract structured entities
    entities = _extract_key_entities(title, analysis)
    
    # Priority 1: Exact title searches (for specific documents)
    if title:
        title_lower = title.lower()
        # Check if it's a specific document/statement
        if any(kw in title_lower for kw in ['statement', 'comunicat', 'nota de premsa', 'press release', 'informe', 'report']):
            queries.append(f'"{title}"')  # Exact phrase search
        
        # Title with date filter if date found
        if entities["dates"]:
            for date in entities["dates"][:2]:  # Use first 2 dates
                queries.append(f'{title} {date}')
        
        queries.append(title)
    
    # Priority 2: Publisher-specific searches with document type
    if publisher:
        # Catalan variants
        if language in {"ca", "es"}:
            queries.append(f"{publisher} comunicat oficial")
            queries.append(f"{publisher} nota de premsa")
            queries.append(f"{publisher} declaració oficial")
            queries.append(f"{publisher} roda de premsa")
        
        # English variants
        queries.append(f"{publisher} press release statement")
        queries.append(f"{publisher} official announcement")
        
        # Domain-specific patterns
        domain_patterns = _get_domain_patterns(publisher, artifact_type)
        for pattern in domain_patterns[:3]:  # Limit to top 3
            if title:
                queries.append(f'{pattern} "{title[:50]}"')  # Use shortened title
    
    # Priority 3: Source-based searches
    source_name = _safe_text(article.source_name)
    source_base = _safe_text(article.source_url_base)
    
    if source_base and title:
        domain = urlparse(source_base).netloc if source_base.startswith('http') else source_base
        # Exclude generic pages and search for press/news sections
        queries.append(f'site:{domain} {title[:80]} (premsa OR prensa OR press OR noticia OR comunicat)')
        queries.append(f'site:{domain} {title[:80]} -home -index -about -associacio -contacte')
    
    # Priority 4: Artifact-type specific searches
    if artifact_type:
        artifact_query = f"{artifact_type} {publisher}".strip()
        if entities["locations"]:
            artifact_query += f" {entities['locations'][0]}"
        queries.append(artifact_query)
        
        # For surveys/reports, search for PDF
        if artifact_type.lower() in ['survey', 'barometer', 'report', 'study']:
            queries.append(f'{artifact_type} {publisher} filetype:pdf')
    
    # Priority 5: Key claims with context
    key_claims = analysis.get("key_claims") or []
    if key_claims and publisher:
        claim_snippet = _safe_text(key_claims[0])[:100]
        queries.append(f'{publisher} "{claim_snippet}"')
    
    # Priority 6: Number/data-based searches (for statistical articles)
    if entities["numbers"] and publisher:
        number_context = ' '.join(str(n) for n in entities["numbers"][:2])
        queries.append(f'{publisher} {number_context} {entities["locations"][0] if entities["locations"] else ""}'.strip())
    
    # Deduplicate and return
    deduped = []
    seen = set()
    for query in queries:
        query = query.strip()
        if query and query not in seen and len(query) > 10:  # Min length filter
            deduped.append(query)
            seen.add(query)
    
    return deduped[:15]  # Limit to top 15 queries to avoid overwhelming the search


def _is_likely_homepage_or_generic(url: str) -> bool:
    """Check if URL is likely a homepage or generic page that shouldn't be used as primary source."""
    if not url:
        return True
    
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip('/')
    
    # Generic paths that are never primary sources
    generic_paths = ['', '/', '/index', '/home', '/about', '/about-us', '/qui-som', '/nosotros', 
                     '/associacio', '/asociacion', '/contact', '/contacte', '/contacto']
    if path in generic_paths:
        return True
    
    # Check for generic path patterns
    generic_patterns = [r'^/[a-z]{2}/?$',  # Just language code like /ca/ or /es/
                       r'^/index\.',  # index.html, index.php
                       r'/home/?$',
                       r'/about/?$']
    for pattern in generic_patterns:
        if re.search(pattern, path):
            return True
    
    return False


def _augment_prompt(base_prompt: str, queries: list[str], fallback: bool = False) -> str:
    if not queries:
        return base_prompt
    
    query_block = "\n".join(f"- {query}" for query in queries)
    extra = "\n\nPRIORITY SEARCH QUERIES (run these first, in order):\n" + query_block
    
    extra += (
        "\n\nURL VALIDATION CHECKLIST (verify EVERY candidate URL):\n"
        "✓ Returns HTTP 200 (not 404, 403, 500)\n"
        "✓ Content actually discusses the article topic\n"
        "✓ Date matches article timeframe (±7 days)\n"
        "✓ Contains specific information mentioned in article (names, numbers, quotes)\n"
        "✓ NOT a homepage (/, /index, /home, /about, /associacio)\n"
        "✓ NOT a category/archive page\n"
        "✓ HAS a specific path like /comunicats/, /premsa/, /noticies/, /press-release/\n"
    )
    
    if fallback:
        extra += (
            "\n\nFALLBACK SEARCH STRATEGY:\n"
            "1. Use site: filters on official domains (gencat.cat, govern.cat, institutional domains)\n"
            "2. Look for press sections: /comunicats/, /premsa/, /prensa/, /press/, /noticies/\n"
            "3. If homepage found, append common press paths and test\n"
            "4. Search for PDF reports if the article mentions a report/study\n"
            "5. Check Internet Archive (archive.org) for removed content\n"
            "6. Use social media (Twitter/X) ONLY as last resort after verifying accessibility\n"
        )
    
    return base_prompt + extra


def _parse_primary(raw: str) -> dict:
    payload = parse_json_response(raw)
    primary = payload.get("primary_source", {}) if isinstance(payload, dict) else {}
    url = primary.get("url")
    if url in {"", "null"}:
        primary["url"] = None
    if "source_type" not in primary:
        primary["source_type"] = "primary"
    
    # Filter out homepage URLs
    if url and _is_likely_homepage_or_generic(url):
        print(f"⚠️  Rejecting homepage/generic URL: {url}")
        primary["url"] = None
        primary["confidence"] = 0.0
    
    # Also check alternatives
    alternatives = payload.get("alternatives", [])
    filtered_alternatives = []
    for alt in alternatives:
        alt_url = alt.get("url", "")
        if alt_url and not _is_likely_homepage_or_generic(alt_url):
            filtered_alternatives.append(alt)
        elif alt_url:
            print(f"⚠️  Filtering out homepage alternative: {alt_url}")
    payload["alternatives"] = filtered_alternatives
    
    return payload


def find_primary_source(article: Article, analysis: dict, api_keys: dict) -> dict:
    article_json = json.dumps(article.to_dict(), ensure_ascii=True, indent=2)
    analysis_json = json.dumps(analysis, ensure_ascii=True, indent=2)
    system_prompt = resolve_prompt(api_keys, "PROMPT_PRIMARY_SYSTEM", PRIMARY_SYSTEM)
    user_template = resolve_prompt(api_keys, "PROMPT_PRIMARY_USER", PRIMARY_USER)
    user_prompt = user_template.replace("<ARTICLE_JSON_HERE>", article_json)
    user_prompt = user_prompt.replace("<ANALYSIS_JSON_HERE>", analysis_json)

    queries = _build_queries(article, analysis)
    user_prompt = _augment_prompt(user_prompt, queries)

    client = GeminiSearchClient(api_key=api_keys["GEMINI_API_KEY"])
    for attempt in range(2):
        raw = client.generate(system_prompt, user_prompt)
        try:
            payload = _parse_primary(raw)
            break
        except LLMError:
            if attempt == 1:
                raise
    else:
        payload = {}

    primary = payload.get("primary_source", {}) if payload else {}
    if primary.get("url"):
        return payload

    # Generate dynamic fallback queries based on article content
    fallback_queries = []
    title = _safe_text(article.title) or _safe_text(article.original_title)
    publisher = _safe_text(analysis.get("probable_primary_publisher"))
    core_topic = _safe_text(analysis.get("core_topic"))
    
    # Build context-specific fallback queries
    if publisher and title:
        # Try official domains with specific topic
        for domain in ["gencat.cat", "govern.cat", "ajuntament.barcelona.cat"]:
            if any(k in publisher.lower() for k in ["generalitat", "govern", "ajuntament"]):
                fallback_queries.append(f'site:{domain} "{title[:60]}"')
                if core_topic:
                    fallback_queries.append(f'site:{domain} {core_topic[:80]}')
    
    # Add generic institutional searches
    if publisher and core_topic:
        fallback_queries.extend([
            f'"{publisher}" {core_topic[:80]} filetype:pdf',
            f'"{publisher}" comunicat {core_topic[:60]}',
            f'"{publisher}" press release {core_topic[:60]}'
        ])
    
    # Add archived content search as last resort
    if title:
        fallback_queries.append(f'site:web.archive.org {title[:80]}')
    
    fallback_queries = fallback_queries[:8]  # Limit to 8 fallback queries
    
    if fallback_queries:
        print(f"🔄 Attempting {len(fallback_queries)} fallback searches...")
        fallback_prompt = _augment_prompt(user_prompt, fallback_queries, fallback=True)
        raw = client.generate(system_prompt, fallback_prompt)
        payload = _parse_primary(raw)
    
    return payload
