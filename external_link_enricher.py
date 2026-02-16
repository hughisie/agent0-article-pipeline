"""
External Link Enricher Module

This module finds and inserts relevant external links into articles.
It uses Perplexity Sonar for web-grounded search to find authoritative sources
for key topics mentioned in the article.

Link categories:
  - Organization/association websites
  - Government/municipal websites
  - Google Maps links for locations mentioned
  - Original source material
  - Source attribution via title hover text
"""

import json
import re
import requests
from typing import Optional
from urllib.parse import urlparse, quote_plus

from llm_clients import PerplexitySonarClient, GeminiClient, GeminiSearchClient, LLMError


# Domains we never link to (news sites, blogs)
# NOTE: wikipedia.org is NOT blocked — it's allowed for non-English term definitions
NEWS_DOMAINS = [
    'news.google', 'elpais.', 'lavanguardia.', 'elperiodico.',
    'ara.cat', 'beteve.', 'elnacional.', 'naciodigital.', 'vilaweb.',
    '324.cat', 'ccma.cat', 'bbc.', 'guardian.', 'reuters.', 'cnn.',
    'nytimes.', 'washingtonpost.', 'france24.', 'euronews.', 'publico.',
    'eldiario.', 'larazon.', 'elmundo.', 'abc.es', 'totbarcelona.',
    'timeout.', 'metropoliabierta.', 'cronicaglobal.',
]

# Well-known organization domains (used for relevance scoring, NOT to skip validation)
KNOWN_ORG_DOMAINS = [
    'barcelona.cat', 'ajuntament.barcelona.cat', 'gencat.cat', 'web.gencat.cat',
    'govern.cat', 'lamoncloa.gob.es', 'mitma.gob.es', 'adif.es', 'renfe.com',
    'tmb.cat', 'fgc.cat', 'aena.es', 'dgt.es', 'boe.es', 'ine.es',
    'bombers.gencat.cat', 'mossos.gencat.cat', 'sem.gencat.cat',
    'meteo.cat', 'aemet.es', 'proteciocivil.gencat.cat',
    'europa.eu', 'ec.europa.eu',
    'google.com', 'maps.google.com', 'www.google.com',
]

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}


def _extract_plain_text(html_content: str, max_chars: int = 2000) -> str:
    """Strip HTML/Gutenberg markup to plain text."""
    text = re.sub(r'<!--[^>]+-->', '', html_content)
    text = re.sub(r'<[^>]+>', '', text)
    return ' '.join(text.split())[:max_chars]


def _extract_locations(text: str) -> list[str]:
    """Extract Barcelona/Catalonia location names from article text."""
    # Well-known neighbourhoods, districts, landmarks
    known_places = [
        'Eixample', 'Gràcia', 'Barceloneta', 'Raval', 'Gótico', 'Born',
        'Sants', 'Les Corts', 'Sarrià', 'Pedralbes', 'Horta', 'Guinardó',
        'Sant Andreu', 'Sant Martí', 'Poblenou', 'Poble Sec', 'Montjuïc',
        'Tibidabo', 'Collserola', 'Sagrada Família', 'Diagonal',
        'La Rambla', 'Passeig de Gràcia', 'Plaça Catalunya', 'Plaça Espanya',
        'Camp Nou', 'Estació de França', 'Sants Estació', 'Zona Franca',
        'El Prat', 'L\'Hospitalet', 'Badalona', 'Santa Coloma',
        'Castelldefels', 'Gavà', 'Sitges', 'Terrassa', 'Sabadell',
        'Mataró', 'Girona', 'Tarragona', 'Lleida', 'Figueres',
        'Montserrat', 'Costa Brava', 'Costa Daurada',
    ]
    found = []
    text_lower = text.lower()
    for place in known_places:
        if place.lower() in text_lower:
            found.append(place)
    return found[:3]  # Max 3 locations


def _extract_organizations(text: str) -> list[str]:
    """Extract organization/institution names from article text."""
    # Common patterns for organizations mentioned in Barcelona/Catalonia news
    org_patterns = [
        r"(?:the\s+)?Ajuntament\s+de\s+\w+",
        r"(?:the\s+)?Generalitat\s+de\s+Catalunya",
        r"(?:the\s+)?Diputaci[oó]\s+de\s+\w+",
        r"(?:the\s+)?Mossos\s+d['']Esquadra",
        r"(?:the\s+)?Bombers\s+de\s+(?:Barcelona|la\s+Generalitat)",
        r"(?:the\s+)?TMB|Transports\s+Metropolitans",
        r"(?:the\s+)?FGC|Ferrocarrils\s+de\s+la\s+Generalitat",
        r"(?:the\s+)?RENFE|Rodalies",
        r"(?:the\s+)?ADIF",
        r"(?:the\s+)?AENA",
        r"(?:the\s+)?Barcelona\s+City\s+Council",
        r"(?:the\s+)?Catalan\s+(?:government|regional\s+government)",
        r"(?:the\s+)?Servei\s+Meteorol[oò]gic",
        r"(?:the\s+)?Protecci[oó]\s+Civil",
        r"(?:the\s+)?Gu[aà]rdia\s+Urbana",
        r"(?:the\s+)?(?:Cruz|Creu)\s+Roja",
        r"(?:the\s+)?SEM|Servei\s+d['']Emerg[eè]ncies",
        # Urban planning / ecology
        r"(?:the\s+)?Directorate\s+of\s+[\w\s]+Services",
        r"(?:the\s+)?Ecologia\s+Urbana",
        r"(?:the\s+)?[AÀ]rea\s+(?:de\s+)?(?:Ecologia|Mobilitat|Urbanisme)[\w\s]*",
        # Education / culture
        r"(?:the\s+)?Escola\s+Industrial",
        r"(?:the\s+)?Escola\s+[A-Z][\w]+",
        r"(?:the\s+)?Universitat\s+(?:de\s+|Polit[eè]cnica|Aut[oò]noma|Pompeu)[\w\s]*",
        # Neighbourhood associations
        r"(?:the\s+)?(?:AVV|Associaci[oó])\s+de\s+Ve[ïi]n[sa]\s+[\w\s']+",
        r"Dreta\s+(?:de\s+l')?Eixample",
        r"Esquerra\s+(?:de\s+l')?Eixample",
        r"Nova\s+Esquerra",
        r"Antiga\s+Esquerra",
        # Police / emergency
        r"(?:the\s+)?Guardia\s+Urbana",
        r"Polic[ií]a\s+Local",
        # Commerce / tourism
        r"Portal\s+de\s+l'[ÀA]ngel",
        r"(?:the\s+)?Tur[iy]?sme\s+de\s+Barcelona",
        r"Visit\s*Barcelona",
        # Superilla / green axes
        r"[Ss]uperilla",
        r"[Ss]uperblock",
        r"green\s+ax[ei]s?",
        r"eix(?:os)?\s+verd[se]?",
    ]
    found = []
    for pattern in org_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches)
    return list(dict.fromkeys(found))[:8]  # Unique, max 8


def _is_news_domain(url: str) -> bool:
    """Check if URL belongs to a news/blocked domain."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in NEWS_DOMAINS)


# Tourism site patterns that are low-value generic district pages
_TOURISM_HOMEPAGE_PATTERNS = [
    r'barcelonaturisme\.com/.*/sants-montjuic',
    r'barcelonaturisme\.com/.*/eixample',
    r'barcelonaturisme\.com/.*/ciutat-vella',
    r'barcelonaturisme\.com/.*/gracia',
    r'barcelonaturisme\.com/.*/les-corts',
    r'barcelonaturisme\.com/.*/sarria',
    r'barcelonaturisme\.com/.*/sant-andreu',
    r'barcelonaturisme\.com/.*/sant-marti',
    r'barcelonaturisme\.com/.*/horta',
    r'barcelonaturisme\.com/.*/nou-barris',
    r'timeout\.com',
]


def _is_homepage(url: str) -> bool:
    """Check if URL is a generic homepage without specific content."""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    if not path or path in ['', '/', '/en', '/es', '/ca', '/index.html', '/home']:
        return True
    # Very short paths that are likely homepages
    if len(path) < 5 and '?' not in url:
        return True
    # Tourism generic district pages (low value for readers)
    url_lower = url.lower()
    if any(re.search(p, url_lower) for p in _TOURISM_HOMEPAGE_PATTERNS):
        return True
    return False


_SOFT_404_TITLE_PATTERNS = [
    # Catalan
    r'no\s+s.ha\s+trobat', r'p[àa]gina\s+no\s+trobad', r'contingut\s+no\s+disponible',
    r'error\s+404', r'error\s+page',
    # Spanish
    r'no\s+encontrad', r'p[áa]gina\s+no\s+encontrad', r'contenido\s+no\s+disponible',
    # English
    r'not\s+found', r'page\s+not\s+found', r'404\s+error', r'404\s+not',
]


def _detect_soft_404(url: str, response: requests.Response) -> bool:
    """Detect soft 404s — pages that return HTTP 200 but don't contain the expected content.
    
    Returns True if the page appears to be a soft 404.
    """
    # Check 1: Did the URL redirect to a significantly different path?
    final_url = response.url
    orig_path = urlparse(url).path.rstrip('/')
    final_path = urlparse(final_url).path.rstrip('/')
    # If redirected to a shorter parent path, likely a soft 404
    if final_path and orig_path and len(final_path) < len(orig_path) * 0.5:
        print(f"    ⚠️ Soft 404: redirected to parent path {final_path}")
        return True

    # Check 2: Examine page content for error indicators
    try:
        content = response.text[:5000] if hasattr(response, 'text') else ''
    except Exception:
        return False

    if not content:
        return False

    # Extract <title> tag
    title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip().lower() if title_match else ''

    # Check title for soft 404 patterns
    for pattern in _SOFT_404_TITLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            print(f"    ⚠️ Soft 404: title contains '{pattern}'")
            return True

    # Check 3: For URLs with specific path segments (e.g., /notes-premsa/12345/...),
    # verify the title isn't just the generic section name
    path_parts = [p for p in orig_path.split('/') if p]
    if len(path_parts) >= 3 and title:
        # If URL has 3+ path segments but title is very short/generic, suspicious
        # E.g., URL: /salapremsa/notes-premsa/445851/long-article-slug
        # Title: "Sala de premsa - Govern.cat" (just the section name)
        slug_words = set()
        for part in path_parts[-2:]:  # Last 2 path segments
            slug_words.update(part.replace('-', ' ').split())
        slug_words = {w.lower() for w in slug_words if len(w) > 4}
        title_words = set(title.lower().split())
        # If none of the slug keywords appear in the title, likely a listing/fallback
        if slug_words and not slug_words.intersection(title_words):
            # Only flag if the path has a specific article slug (>20 chars)
            if any(len(p) > 20 for p in path_parts):
                print(f"    ⚠️ Soft 404: page title doesn't match URL slug")
                return True

    return False


def _quick_validate_url(url: str, timeout: int = 12) -> bool:
    """Strict HTTP validation - EVERY URL is checked with soft 404 detection.
    
    Returns True only if:
    1. HTTP status < 400
    2. Page is not a soft 404 (generic listing/error page)
    
    Google Maps search URLs are exempt.
    """
    if not url or not url.startswith('http'):
        return False

    # Google Maps search URLs always work (they redirect to maps)
    if 'google.com/maps/search/' in url:
        return True

    try:
        # Use GET (not HEAD) so we can check content for soft 404s
        resp = requests.get(url, allow_redirects=True, timeout=timeout, headers=_BROWSER_HEADERS,
                           stream=False)
        if resp.status_code >= 400:
            return False
        # Check for soft 404s (HTTP 200 but page is actually an error/listing page)
        if _detect_soft_404(url, resp):
            return False
        return True
    except requests.RequestException:
        return False


def _parse_json_from_response(text: str) -> list:
    """Extract JSON array from LLM response, handling markdown code blocks."""
    clean = text
    if '```json' in clean:
        clean = clean.split('```json')[1].split('```')[0]
    elif '```' in clean:
        clean = clean.split('```')[1].split('```')[0]
    match = re.search(r'\[[\s\S]*\]', clean)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


def _build_google_maps_url(place_name: str, city: str = "Barcelona") -> str:
    """Build a Google Maps search URL for a location."""
    query = f"{place_name}, {city}, Catalonia"
    return f"https://www.google.com/maps/search/{quote_plus(query)}"


def _extract_entities(text: str, title: str) -> list[str]:
    """Extract specific named entities (businesses, venues, streets, landmarks) from article text.
    
    Goes beyond organizations to find restaurants, shops, streets, parks, buildings etc.
    that readers would want to look up.
    """
    entities = []
    combined = f"{title} {text}"
    
    # Pattern: "Can X" (common Catalan restaurant/venue naming)
    for m in re.finditer(r'\bCan\s+([A-Z][a-zà-ÿ]+)', combined):
        entities.append(f"Can {m.group(1)}")
    
    # Pattern: "Cal X" / "Ca l'X" (Catalan restaurant naming)
    for m in re.finditer(r"\bCa[l]?\s+(?:l')?([A-Z][a-zà-ÿ]+)", combined):
        entities.append(f"Cal {m.group(1)}")
    
    # Pattern: "Mercat de X" / "Mercat del X"
    for m in re.finditer(r'\bMercat\s+(?:de\s+(?:la\s+)?|del?\s+)([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)', combined):
        entities.append(f"Mercat de {m.group(1)}")
    
    # Pattern: Street names - "Carrer de X" / "Carrer X" / "Torrent de X"
    for m in re.finditer(r'\b(?:Carrer|Torrent|Avinguda|Passeig|Rambla)\s+(?:de\s+(?:la\s+|l\')?|del?\s+)?([A-Z][^\s,\.]{2,}(?:\s+(?:de\s+(?:la\s+)?)?[A-Z][^\s,\.]+)*)', combined):
        entities.append(m.group(0))
    
    # Pattern: Named streets without prefix (common BCN streets)
    _KNOWN_STREETS = [
        'Consell de Cent', 'Rocafort', 'Borrell', 'Comte Borrell',
        'Girona', 'Enric Granados', 'Arag[oó]', 'Mallorca',
        'Val[eè]ncia', 'Proven[çc]a', 'Rossell[oó]', 'C[oò]rsega',
        'Balmes', 'Muntaner', 'Aribau', 'Urgell', 'Villarroel',
        'Calabria', 'Tamarit', 'Manso', 'Parallel',
    ]
    for street in _KNOWN_STREETS:
        if re.search(rf'\b{street}\b', combined, re.IGNORECASE):
            # Use the clean version without regex chars
            clean = re.sub(r'\[.*?\]', lambda m: m.group(0)[1], street)
            entities.append(clean)
    
    # Pattern: "Palau X" / "Museu X" / "Parc X" / "Hospital X" / "Escola X"
    for m in re.finditer(r'\b(?:Palau|Museu|Parc|Hospital|Teatre|Fundaci[oó]|Escola|Biblioteca|Centre)\s+(?:de\s+(?:la\s+)?|del?\s+)?([A-Z][a-zà-ÿA-Z]+(?:\s+[A-Z][a-zà-ÿA-Z]*){0,2})', combined):
        entities.append(m.group(0))
    
    # Pattern: "Portal de l'Àngel" / "Plaça X" / "Parc X"
    for m in re.finditer(r'\b(?:Portal|Pla[çc]a|Jardins|Jard[ií])\s+(?:de\s+(?:la\s+|l\')?|del?\s+)?([A-Z][^\s,\.]{2,}(?:\s+[^\s,\.]+){0,2})', combined):
        entities.append(m.group(0))
    
    # Pattern: Neighbourhood associations - "Dreta", "Esquerra de l'Eixample"
    for m in re.finditer(r'\b(?:Dreta|Esquerra|Nova\s+Esquerra|Antiga\s+Esquerra)(?:\s+(?:de\s+l\')?Eixample)?', combined):
        entities.append(m.group(0))
    
    # Pattern: Superilla / Superblock references
    for m in re.finditer(r'\b[Ss]uperilla(?:\s+(?:de\s+(?:la\s+|l\')?)?\w+)?', combined):
        entities.append(m.group(0))
    
    # Pattern: Business/Brand + Location (e.g., "DiR Tuset", "DiR Diagonal", "Gym Holmes Place")
    # Catches capitalized brand names followed by a known location or street name
    _LOCATION_SUFFIXES = [
        'Tuset', 'Diagonal', 'Sants', 'Eixample', 'Poblenou', 'Gr[aà]cia',
        'Born', 'Raval', 'G[oò]tic', 'Barceloneta', 'Pedralbes', 'Sarri[aà]',
        'Les Corts', 'Horta', 'Sant Gervasi', 'Bonanova', 'Putxet',
        'Mandri', 'Balmes', 'Muntaner', 'Aribau', 'Rocafort',
    ]
    for suffix in _LOCATION_SUFFIXES:
        for m in re.finditer(rf'\b([A-Z][A-Za-zÀ-ÿ]{{1,15}})\s+{suffix}\b', combined):
            full_match = m.group(0)
            brand = m.group(1)
            # Skip common words that aren't brand names
            if brand.lower() not in {'the', 'and', 'for', 'via', 'del', 'des', 'from', 'near', 'next'}:
                entities.append(full_match)
    
    # Pattern: Repeated capitalized name that's likely a brand (appears 3+ times)
    # This catches business names like "DiR" that appear throughout the article
    words = re.findall(r'\b([A-Z][A-Za-zÀ-ÿ]{1,20})\b', combined)
    word_counts = {}
    for w in words:
        if len(w) >= 2 and w.lower() not in {
            'the', 'and', 'for', 'but', 'not', 'was', 'has', 'had', 'its',
            'new', 'said', 'also', 'will', 'been', 'from', 'with', 'this',
            'that', 'they', 'their', 'more', 'than', 'about', 'which',
            'would', 'could', 'should', 'into', 'over', 'after', 'before',
            'barcelona', 'catalonia', 'catalan', 'spain', 'spanish',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
            'saturday', 'sunday', 'january', 'february', 'march', 'april',
            'may', 'june', 'july', 'august', 'september', 'october',
            'november', 'december', 'according', 'however', 'meanwhile',
        }:
            word_counts[w] = word_counts.get(w, 0) + 1
    already_found = {e.strip().lower() for e in entities}
    for word, count in word_counts.items():
        if count >= 3 and word.lower() not in already_found:
            entities.append(word)
    
    # Deduplicate preserving order
    seen = set()
    unique = []
    for e in entities:
        e_clean = e.strip()
        if e_clean.lower() not in seen and len(e_clean) > 2:
            seen.add(e_clean.lower())
            unique.append(e_clean)
    return unique[:10]


def find_relevant_external_links(
    article_content: str,
    article_title: str,
    primary_keyword: str,
    api_key: str,
    source_url: str = "",
    source_name: str = "",
    max_links: int = 3,
    gemini_api_key: str = "",
) -> list[dict]:
    """
    Find relevant external links using dual-engine search:
      1. Perplexity Sonar for authoritative/government links
      2. Gemini Flash with Google Search for entity-specific links (businesses, venues, local pages)
      3. Google Maps for key locations

    All discovered URLs are strictly HTTP-validated with soft 404 detection.

    Args:
        api_key: Perplexity Sonar API key
        gemini_api_key: Gemini API key for Google Search grounding (optional secondary engine)

    Returns:
        List of dicts: url, anchor_text, topic, link_type, source_attribution
    """
    if not api_key and not gemini_api_key:
        print("  ⚠️  No API keys for external link search")
        return []

    # Ensure primary_keyword is not empty
    if not primary_keyword or not primary_keyword.strip():
        primary_keyword = article_title.split()[0] if article_title and article_title.strip() else "Barcelona"

    plain_text = _extract_plain_text(article_content)
    locations = _extract_locations(plain_text)
    organizations = _extract_organizations(plain_text)
    entities = _extract_entities(plain_text, article_title)

    all_links = []

    # --- Strategy 1: Perplexity Sonar web-grounded search ---
    if api_key:
        try:
            client = PerplexitySonarClient(api_key=api_key)
            perplexity_prompt = f"""Find official, authoritative external links for this Barcelona/Catalonia news article.

ARTICLE TITLE: {article_title}
ORGANIZATIONS MENTIONED: {', '.join(organizations) if organizations else 'None detected'}
LOCATIONS MENTIONED: {', '.join(locations) if locations else 'None detected'}
SPECIFIC ENTITIES (businesses, venues, streets): {', '.join(entities) if entities else 'None detected'}

ARTICLE EXCERPT:
{plain_text[:2000]}

Find up to {max_links + 4} links. Search THOROUGHLY across ALL categories:

1. BUSINESS/VENUE WEBSITES - official website or social media of any business, restaurant, venue, or shop mentioned
   (e.g., their .com, .cat, .es website, or their Facebook/Instagram page)
2. OFFICIAL ORGANIZATION WEBSITES - websites of organizations/institutions mentioned
   (e.g., tmb.cat, renfe.com, ajuntament.barcelona.cat)
3. BARCELONA CITY COUNCIL PROJECT PAGES - specific ajuntament.barcelona.cat pages for projects, districts, or services
   (e.g., ajuntament.barcelona.cat/superilla, ajuntament.barcelona.cat/ecologiaurbana)
4. NEIGHBOURHOOD / DISTRICT PAGES - Barcelona district or neighbourhood association websites
   (e.g., ajuntament.barcelona.cat/eixample, avvdretaeixample.cat, avveixample.cat)
5. WIKIPEDIA TERM DEFINITIONS - if the article mentions a non-English cultural term or concept
   (e.g., botellón, castellera, diada, calçotada, correfoc), link to its Wikipedia page
   ONLY for explaining foreign/cultural terms readers may not know, NOT for general topics
6. GOOGLE MAPS FOR SPECIFIC LOCATIONS - for specific streets, paths, parks, or venues mentioned
   (e.g., Camí de la Foixarda, Carrer de Consell de Cent) — use Google Maps search URLs
7. SPECIFIC STREET/PROJECT PAGES - pages about specific streets, green axes, superblocks
   (e.g., barcelona.cat/en/living-in-bcn/moving-around-the-city/streets/)

CRITICAL RULES:
- ONLY return URLs that ACTUALLY EXIST and are currently live
- NO news sites (except the business's OWN blog/news page is OK)
- Wikipedia is ONLY acceptable for explaining non-English cultural terms (e.g., botellón, castellera)
- Facebook pages of specific businesses ARE acceptable
- Neighbourhood association homepages (.cat domains) ARE acceptable
- Each URL must be a real, working page you can verify
- Include the organization/business name for source attribution
- Prefer specific sub-pages over generic homepages
- Prefer Google Maps over tourism websites for district/neighbourhood links
- Do NOT link to barcelonaturisme.com generic district pages
- If the article is ABOUT a specific business/company, their official website is the HIGHEST PRIORITY link
- For businesses with multiple locations, include Google Maps links to specific branches mentioned

Return a JSON array:
[
  {{
    "url": "https://example.cat/specific-page",
    "anchor_text": "Short text for the link (2-5 words)",
    "topic": "What this link covers",
    "link_type": "business|organization|government|neighbourhood|topic_page|street_project|wikipedia_term|google_maps",
    "source_attribution": "Name of the organization or publisher"
  }}
]

If you cannot find real, verified sources, return [].
"""
            response_text = client.generate(
                system_prompt="You are a research assistant finding authoritative external links for news articles. Return only valid JSON arrays. Only include URLs you are confident actually exist.",
                user_prompt=perplexity_prompt,
            ).strip()

            if '__CITATIONS__:' in response_text:
                response_text = response_text.split('__CITATIONS__:')[0].strip()

            links = _parse_json_from_response(response_text)
            for link in links:
                url = link.get('url', '')
                if not url or not url.startswith('http'):
                    continue
                if _is_news_domain(url):
                    continue
                link.setdefault('link_type', 'organization')
                link.setdefault('source_attribution', '')
                link['_source'] = 'perplexity'
                all_links.append(link)
            print(f"    Perplexity found {len(all_links)} candidate links")

        except Exception as e:
            print(f"  ⚠️  Perplexity search error: {e}")

    # --- Strategy 2: Gemini Flash with Google Search grounding ---
    # Always run Gemini Search as secondary engine - it uses Google's index
    # and finds entity-specific links that Perplexity may miss
    if gemini_api_key:
        try:
            gemini_search = GeminiSearchClient(api_key=gemini_api_key)
            # Build search context from entities, orgs, locations, and title
            search_items = entities[:6] + organizations[:3] + locations[:2]
            search_context = ', '.join(search_items) if search_items else article_title
            gemini_prompt = f"""Search Google for the official websites and pages related to these items from a Barcelona/Catalonia news article:

ITEMS TO SEARCH: {search_context}
ARTICLE TITLE: {article_title}
ARTICLE EXCERPT: {plain_text[:1000]}

For EACH item, search Google and find:
- Their official website (.com, .cat, .es, .org)
- Their page on ajuntament.barcelona.cat (city council project pages, district pages)
- Their page on visitbarcelona.com or meet.barcelona
- Neighbourhood association websites (e.g., avvdretaeixample.cat)
- Facebook/Instagram pages of businesses

Return a JSON array with ONLY real URLs you found via Google Search:
[
  {{
    "url": "https://...",
    "anchor_text": "Short link text (2-5 words)",
    "topic": "What this link covers",
    "link_type": "business|organization|government|neighbourhood|street_project",
    "source_attribution": "Entity name"
  }}
]

CRITICAL: Only include URLs you actually found in Google Search results. Do NOT invent URLs. Return [] if nothing found.
"""
            gemini_response = gemini_search.generate(
                system_prompt="Find real URLs via Google Search. Return valid JSON only.",
                user_prompt=gemini_prompt,
            ).strip()

            gemini_links = _parse_json_from_response(gemini_response)
            existing_urls = {link.get('url', '').lower() for link in all_links}
            for link in gemini_links:
                url = link.get('url', '')
                if not url or not url.startswith('http'):
                    continue
                if url.lower() in existing_urls:
                    continue
                if _is_news_domain(url):
                    continue
                link.setdefault('link_type', 'business')
                link.setdefault('source_attribution', '')
                link['_source'] = 'gemini'
                all_links.append(link)
            print(f"    Gemini added {sum(1 for l in all_links if l.get('_source') == 'gemini')} additional candidates")

        except Exception as e:
            print(f"  ⚠️  Gemini entity search error: {e}")

    # --- Strategy 3: Google Maps links for key locations and specific entities ---
    maps_added = 0
    for loc in locations[:2]:
        maps_url = _build_google_maps_url(loc)
        all_links.append({
            "url": maps_url,
            "anchor_text": loc,
            "topic": f"Location: {loc}",
            "link_type": "google_maps",
            "source_attribution": "Google Maps",
        })
        maps_added += 1
        print(f"    📍 Added Google Maps link for: {loc}")
    # Also add maps links for specific street/venue entities not already covered
    for entity in entities[:3]:
        if maps_added >= 3:
            break
        entity_lower = entity.lower()
        if any(entity_lower == loc.lower() for loc in locations[:2]):
            continue
        if any(kw in entity_lower for kw in ['carrer', 'camí', 'avinguda', 'passeig', 'rambla', 'plaça', 'parc', 'jardins', 'club', 'gym', 'centre', 'center', 'hotel', 'restaurant', 'mercat', 'museu', 'teatre', 'cinema', 'hospital']):
            maps_url = _build_google_maps_url(entity)
            all_links.append({
                "url": maps_url,
                "anchor_text": entity,
                "topic": f"Location: {entity}",
                "link_type": "google_maps",
                "source_attribution": "Google Maps",
            })
            maps_added += 1
            print(f"    📍 Added Google Maps link for entity: {entity}")

    # --- Validate and deduplicate ---
    seen_domains = set()
    verified = []
    for link in all_links:
        url = link.get('url', '')
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip('www.')
        is_maps = link.get('link_type') == 'google_maps'

        # Skip duplicate domains (but exempt google_maps links)
        if domain in seen_domains and not is_maps:
            continue

        # Skip homepages unless it's an org, business, neighbourhood, maps, or wikipedia link
        if _is_homepage(url) and link.get('link_type') not in ('organization', 'business', 'neighbourhood', 'google_maps', 'street_project', 'wikipedia_term'):
            continue

        # Google Maps links are always valid
        if is_maps or _quick_validate_url(url):
            if not is_maps:
                seen_domains.add(domain)
            # Clean up internal tracking field
            link.pop('_source', None)
            verified.append(link)
            if len(verified) >= max_links + 2:  # Allow extras for better selection
                break
        else:
            print(f"    ⚠️ Skipping broken URL: {url[:60]}...")

    return verified[:max_links]


def integrate_external_links(
    content: str,
    links: list[dict],
    api_key: str,
) -> tuple[str, int]:
    """
    Integrate external links naturally into the article content using Gemini.

    Links include title attributes for source attribution on hover.
    """
    if not links or not api_key:
        return content, 0

    client = GeminiClient(api_key=api_key, model="gemini-2.5-flash")

    # Build link specifications with hover text
    link_specs = []
    for link in links:
        source_attr = link.get('source_attribution', '')
        title_attr = f' title="Source: {source_attr}"' if source_attr else ''
        link_specs.append({
            "url": link['url'],
            "anchor_text": link.get('anchor_text', ''),
            "topic": link.get('topic', ''),
            "link_type": link.get('link_type', ''),
            "html_format": f'<a href="{link["url"]}"{title_attr} target="_blank" rel="noopener">[ANCHOR]</a>',
        })

    links_json = json.dumps(link_specs, indent=2)

    prompt = f"""You are integrating external links into a news article.

LINKS TO ADD:
{links_json}

ARTICLE CONTENT:
{content}

YOUR TASK:
Integrate these links naturally into the article. For each link:

1. Find a RELEVANT sentence where the link topic is mentioned
2. Replace appropriate words with the linked version
3. Use the exact html_format provided, replacing [ANCHOR] with natural anchor text (2-5 words)
4. For Google Maps links: link the location name where it first appears

STRICT RULES:
- Links MUST be integrated WITHIN existing sentences
- NEVER append links at the end of paragraphs
- NEVER add "For more information" or "Visit the website" sentences
- NEVER change article structure or add new paragraphs
- If a link cannot be naturally integrated, SKIP it entirely
- Preserve ALL existing links and content exactly

REMOVE any existing sentences like:
- "For more information on X, you can refer to Y"
- "Visit the X website for more details"

Return ONLY the updated article content, nothing else."""

    try:
        updated = client.generate(
            system_prompt="You are an expert editor integrating links into news articles. Return only the updated content.",
            user_prompt=prompt,
        ).strip()

        # Clean markdown wrappers
        if '```html' in updated:
            updated = updated.split('```html')[1].split('```')[0].strip()
        elif '```' in updated:
            parts = updated.split('```')
            if len(parts) >= 3:
                updated = parts[1].strip()

        # Verify content validity
        if '<!-- wp:' not in updated:
            print("  ⚠️  Link integration returned invalid content, keeping original")
            return content, 0

        # Count links added
        links_added = sum(1 for link in links if link.get('url') and link['url'] in updated)
        return updated, links_added

    except Exception as e:
        print(f"  ⚠️  Link integration error: {e}")
        return content, 0


def add_source_attribution(content: str, source_url: str, source_name: str) -> str:
    """
    Add title hover text to source links for attribution.
    Finds existing links to the source URL and adds title="Source: X" attribute.
    """
    if not content or not source_url or not source_name:
        return content

    # Find links to this source URL that don't already have a title
    pattern = re.compile(
        r'(<a\s+[^>]*href=["\']' + re.escape(source_url) + r'["\'])([^>]*>)',
        re.IGNORECASE
    )

    def _add_title(match):
        before_close = match.group(1)
        after = match.group(2)
        if 'title=' in before_close or 'title=' in after:
            return match.group(0)  # Already has title
        return f'{before_close} title="Source: {source_name}"{after}'

    return pattern.sub(_add_title, content)


def enrich_article_with_external_links(
    content: str,
    article_title: str,
    primary_keyword: str,
    api_key: str = "",
    source_url: str = "",
    source_name: str = "",
    max_links: int = 3,
    perplexity_api_key: str = "",
    gemini_api_key: str = "",
) -> tuple[str, dict]:
    """
    Main function to enrich an article with relevant external links.
    Uses Perplexity Sonar for link discovery, Gemini for link integration.
    All links are HTTP-validated before insertion.

    Args:
        api_key: Deprecated - use perplexity_api_key instead
        perplexity_api_key: Perplexity Sonar API key for web search
        gemini_api_key: Gemini API key for link integration into content
    """
    # Support both old api_key param and new specific params
    search_key = perplexity_api_key or api_key
    integration_key = gemini_api_key or api_key

    report = {
        "links_found": 0,
        "links_added": 0,
        "links": [],
        "maps_links": 0,
    }

    print("--- External Link Enrichment (Dual Engine: Perplexity + Gemini) ---")

    if not search_key and not integration_key:
        print("  ⚠️  No API keys - skipping external link search")
        return content, report

    # Step 1: Find relevant links via dual-engine search
    print("  Searching for relevant external links...")
    links = find_relevant_external_links(
        article_content=content,
        article_title=article_title,
        primary_keyword=primary_keyword,
        api_key=search_key,
        source_url=source_url,
        source_name=source_name,
        max_links=max_links,
        gemini_api_key=integration_key,
    )

    report["links_found"] = len(links)
    report["links"] = links
    report["maps_links"] = sum(1 for l in links if l.get('link_type') == 'google_maps')

    if not links:
        print("  No relevant external links found")
        return content, report

    print(f"  Found {len(links)} relevant links:")
    for link in links:
        ltype = link.get('link_type', '?')
        print(f"    [{ltype}] {link.get('url', 'N/A')[:70]}")
        print(f"      Anchor: {link.get('anchor_text', 'N/A')}")

    # Step 2: Integrate links into content (uses Gemini for natural text editing)
    print("  Integrating links into article...")
    enriched, links_added = integrate_external_links(content, links, integration_key)

    # Step 3: Add source attribution hover text
    if source_url and source_name:
        enriched = add_source_attribution(enriched, source_url, source_name)

    report["links_added"] = links_added
    print(f"  Links added: {links_added}")

    return enriched, report


def remove_generic_resource_sentences(content: str) -> str:
    """
    Remove generic "For more information" sentences that don't have actual links.
    These sentences are unhelpful without hyperlinks and should be removed.
    """
    patterns = [
        r'For more information[^.]*\.',
        r'For broader context[^.]*\.',
        r'For further context[^.]*\.',
        r'Furthermore,?\s+you can learn more[^.]*\.',
        r'You can learn more[^.]*\.',
        r'Visit the[^.]*website[^.]*\.',
        r'You can refer to[^.]*\.',
        r'you can visit the[^.]*\.',
        r'For further reading[^.]*\.',
        r'More details can be found[^.]*\.',
        r'To learn more about[^.]*\.',
        r'For additional information[^.]*\.',
        r'[,;]\s*see this[^.]*report[^.]*\.',
        r'[Rr]efer to the[^.]*\.',
    ]

    for pattern in patterns:
        matches = list(re.finditer(pattern, content, re.IGNORECASE))
        for match in reversed(matches):
            sentence = match.group()
            if '<a href=' not in sentence:
                content = content[:match.start()] + content[match.end():]

    content = re.sub(r'<p>\s*</p>', '', content)
    content = re.sub(r'<!-- wp:paragraph -->\s*<!-- /wp:paragraph -->', '', content)

    return content
