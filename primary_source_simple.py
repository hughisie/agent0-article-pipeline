"""
Enhanced primary source finder using Gemini with Google Search.
Uses multi-strategy approach with institutional knowledge base.
"""
import json
import re
from pathlib import Path
from typing import Optional

from llm_clients import GeminiSearchClient, LLMError


# Load knowledge base
_KNOWLEDGE_BASE = None

def _load_knowledge_base() -> dict:
    """Load the institutional knowledge base."""
    global _KNOWLEDGE_BASE
    if _KNOWLEDGE_BASE is not None:
        return _KNOWLEDGE_BASE
    
    kb_path = Path(__file__).parent / "primary_source_knowledge_base.json"
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            _KNOWLEDGE_BASE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _KNOWLEDGE_BASE = {"domains": {}, "search_strategies": {}}
    
    return _KNOWLEDGE_BASE


def _get_priority_domains(publisher: str, artifact_type: str = None) -> list[str]:
    """Get priority domains based on publisher and artifact type."""
    kb = _load_knowledge_base()
    domains = kb.get("domains", {})
    
    priority = []
    publisher_lower = (publisher or "").lower()
    
    # Match by artifact type first (most specific)
    if artifact_type:
        artifact_lower = artifact_type.lower()
        for domain, info in domains.items():
            domain_types = [t.lower() for t in info.get("artifact_types", [])]
            if any(at in artifact_lower or artifact_lower in at for at in domain_types):
                if domain not in priority:
                    priority.append(domain)
    
    # Match by publisher name keywords
    _PUBLISHER_KEYWORDS = {
        "bombers": ["bombers.gencat.cat"],
        "mossos": ["mossos.gencat.cat", "interior.gencat.cat"],
        "trànsit": ["transit.gencat.cat"],
        "transit": ["transit.gencat.cat"],
        "guàrdia urbana": ["guardiaurbana.bcn.cat", "ajuntament.barcelona.cat"],
        "guardia urbana": ["guardiaurbana.bcn.cat", "ajuntament.barcelona.cat"],
        "sem": ["sem.gencat.cat"],
        "emergències": ["sem.gencat.cat", "interior.gencat.cat"],
        "govern": ["govern.cat"],
        "generalitat": ["govern.cat", "gencat.cat"],
        "ajuntament": ["ajuntament.barcelona.cat"],
        "sip-fepol": ["sipfepol.cat"],
        "sipfepol": ["sipfepol.cat"],
    }
    for keyword, kw_domains in _PUBLISHER_KEYWORDS.items():
        if keyword in publisher_lower:
            for d in kw_domains:
                if d not in priority:
                    priority.append(d)
    
    # Match by publisher name or publisher_keywords in knowledge base
    for domain, info in domains.items():
        name_lower = info.get("name", "").lower()
        if publisher_lower and (publisher_lower in name_lower or name_lower in publisher_lower):
            if domain not in priority:
                priority.append(domain)
        # Also check publisher_keywords field
        for kw in info.get("publisher_keywords", []):
            if kw.lower() in publisher_lower:
                if domain not in priority:
                    priority.insert(0, domain)
                break
    
    # Always include govern.cat/salapremsa for government press releases
    if "govern.cat" not in priority:
        priority.append("govern.cat")
    
    # Add high-priority Catalan/Spanish government domains
    high_priority = [d for d, info in domains.items() if info.get("priority") == "high"]
    for d in high_priority:
        if d not in priority:
            priority.append(d)
    
    # Try to infer the publisher's own domain.
    # Extract short name before parentheses: "SIP-FEPOL (police union)" → "SIP-FEPOL"
    if publisher_lower:
        short_name = re.split(r'\s*[\(\[/,–—]', publisher_lower)[0].strip()
        # Only check government keywords against the short name, not descriptions
        is_govt = any(kw in short_name for kw in {
            'ajuntament', 'generalitat', 'govern', 'mossos', 'bombers',
            'guardia', 'guàrdia', 'transit', 'trànsit', 'sem',
            'government', 'council', 'department', 'authority',
            'municipal', 'ministry', 'junta', 'diputació', 'policia',
        })
        if not is_govt:
            # Keep hyphens (common in org domains like sip-fepol.cat)
            publisher_slug = re.sub(r'[^a-z0-9\-]', '', short_name).strip('-')
            if publisher_slug and 2 <= len(publisher_slug) <= 20:
                for tld in ['.cat', '.com', '.es']:
                    candidate = f"{publisher_slug}{tld}"
                    if candidate not in priority:
                        priority.insert(0, candidate)
    
    return priority[:7]  # Limit to top 7


# Known government/institutional keywords — if publisher matches, it's NOT a business
_GOVERNMENT_KEYWORDS = {
    'ajuntament', 'generalitat', 'govern', 'mossos', 'bombers', 'policia',
    'guardia', 'guàrdia', 'transit', 'trànsit', 'sem', 'emergències',
    'diputació', 'parlament', 'ministerio', 'gobierno', 'council', 'government',
    'department', 'authority', 'police', 'municipal', 'ministry', 'junta',
    'seguridad', 'security', 'protecció', 'civil',
}


def _is_likely_business(publisher: str) -> bool:
    """Check if the publisher looks like a business/company rather than government."""
    if not publisher:
        return False
    publisher_lower = publisher.lower()
    return not any(kw in publisher_lower for kw in _GOVERNMENT_KEYWORDS)


def _build_targeted_queries(title: str, publisher: str, priority_domains: list[str]) -> list[str]:
    """Build targeted search queries using priority domains."""
    queries = []
    
    # Extract key terms from title
    title_clean = re.sub(r'[^\w\s]', '', title)
    key_terms = ' '.join(title_clean.split()[:8])  # First 8 words
    
    # Site-specific queries for priority domains
    for domain in priority_domains[:3]:
        queries.append(f"site:{domain} {key_terms}")
    
    # General query with publisher
    if publisher:
        queries.append(f"{publisher} comunicat {key_terms}")
        queries.append(f"{publisher} nota de premsa {key_terms}")
    
    # Business/company-specific queries
    if publisher and _is_likely_business(publisher):
        queries.append(f"{publisher} blog {key_terms}")
        queries.append(f"{publisher} press release {key_terms}")
        queries.append(f"{publisher} official website {key_terms}")
        # Try site-specific search on likely company domain
        publisher_slug = re.sub(r'[^a-z0-9]', '', publisher.lower())
        if publisher_slug:
            for tld in ['.cat', '.com', '.es']:
                queries.append(f"site:{publisher_slug}{tld} {key_terms}")
    
    # Catalan/Spanish language queries
    queries.append(f"comunicat oficial {key_terms}")
    queries.append(f"nota de prensa {key_terms}")
    
    return queries


def find_primary_source_simple(
    title: str,
    publisher: str,
    summary: str,
    api_key: str,
    artifact_type: str = None,
) -> dict:
    """
    Enhanced primary source finder using Gemini with Google Search grounding.
    
    Uses multi-strategy approach:
    1. Identify priority domains from knowledge base
    2. Build targeted queries
    3. Search with Gemini + Google Search
    4. Validate and rank results
    """
    print(f"  - Searching for primary source...")
    print(f"  - Title: {title[:80]}..." if len(title) > 80 else f"  - Title: {title}")
    print(f"  - Publisher hint: {publisher or 'none'}")
    
    # Get priority domains from knowledge base
    priority_domains = _get_priority_domains(publisher, artifact_type)
    if priority_domains:
        print(f"  - Priority domains: {', '.join(priority_domains[:3])}")
    
    # Build targeted queries
    targeted_queries = _build_targeted_queries(title, publisher, priority_domains)
    
    client = GeminiSearchClient(api_key=api_key)
    
    is_business = _is_likely_business(publisher)
    
    system_prompt = """You are a research assistant finding the ORIGINAL PRIMARY SOURCE for a news article.

Use Google Search to find the OFFICIAL source where this information was first published.

SEARCH FOR:
- Official press releases from governments, institutions, organizations
- Official announcements on .gov, .edu, or institutional websites
- Original reports, studies, or documents (PDFs are good)
- Official statements from the organization mentioned
- Company/business blog posts, press pages, or news announcements on the company's OWN website
  (e.g., /blog/, /news/, /press/, /noticias/, /novedades/)
- Corporate communications published by the business itself

IMPORTANT: If the article is about a specific BUSINESS or COMPANY, their own website's blog or
press page is often the primary source. Search the company's domain directly.

DO NOT RETURN:
- News article URLs (BBC, Guardian, Reuters, etc.)
- Generic homepages (just "/" or "/about")
- Social media posts
- Wikipedia

Return ONLY valid JSON:
{
  "primary_source": {
    "url": "https://specific-url-to-document-or-press-release",
    "title": "Title of the source document",
    "publisher": "Organization name",
    "confidence": 0.0-1.0
  }
}

If you cannot find a specific official source, return {"primary_source": {"url": null, "confidence": 0.0}}"""

    # Build a focused search query with targeted queries
    priority_domains_str = ", ".join(priority_domains[:3]) if priority_domains else "gencat.cat, govern.cat, ajuntament.barcelona.cat"
    suggested_queries_str = "\n".join(f"  - {q}" for q in targeted_queries[:5])
    
    search_query = f"""Find the original official source for this news:

Title: {title}
Publisher/Organization: {publisher}
Summary: {summary[:400]}

PRIORITY DOMAINS TO SEARCH (try these first):
{priority_domains_str}

SUGGESTED SEARCH QUERIES:
{suggested_queries_str}

IMPORTANT SEARCH STRATEGIES:
1. For government announcements: search govern.cat/salapremsa/notes-premsa/ — this is the Catalan government press room
2. For traffic/road incidents: search transit.gencat.cat for the specific incident report
3. For fire/rescue: search bombers.gencat.cat for the specific operation report
4. For police: search mossos.gencat.cat or interior.gencat.cat
5. For Barcelona municipal: search ajuntament.barcelona.cat/premsa/
6. For Catalan government departments: search gencat.cat or web.gencat.cat
7. For BUSINESSES/COMPANIES: search the company's OWN website for blog posts or press releases
   - Try site:[company].cat, site:[company].com, site:[company].es
   - Look for /blog/, /news/, /press/, /noticias/ sections
   - Example: for DiR fitness, search site:dir.cat blog

Search for the official press release, announcement, document, or company blog post.
Look for URLs with specific paths like /noticies/, /actualitat/, /premsa/, /comunicats/, /salapremsa/, /blog/, /news/, /press/.
Return the specific URL to the document, not a homepage.
If you find a PDF document, that's often the best source."""

    try:
        raw = client.generate(system_prompt, search_query)
        
        # Parse response — handle markdown-wrapped JSON, extra commentary, etc.
        try:
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'```\s*$', '', cleaned)
            
            # Try direct parse, then regex extraction
            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError:
                match = re.search(r'\{[^{}]*"primary_source"[^{}]*\{[^}]+\}[^}]*\}', cleaned, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                else:
                    # Broader regex for any JSON object
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if match:
                        result = json.loads(match.group(0))
                    else:
                        raise json.JSONDecodeError('No JSON found', cleaned, 0)
            
            primary = result.get('primary_source', {})
            
            # Validate URL is not a homepage
            url = primary.get('url')
            if url:
                print(f"  - Candidate URL found: {url}")
                
                # Parse URL to check path
                from urllib.parse import urlparse
                parsed = urlparse(url)
                path = parsed.path.rstrip('/')
                
                # Reject news site URLs
                news_domains = ['bbc.', 'guardian.', 'reuters.', 'cnn.', 'nytimes.', 'washingtonpost.',
                               'elpais.', 'lavanguardia.', 'elperiodico.', 'ara.cat', 'beteve.', 
                               'elnacional.', 'naciodigital.', 'vilaweb.', '324.cat', 'ccma.cat']
                if any(nd in url.lower() for nd in news_domains):
                    print(f"  - REJECTED: URL is a news site")
                    primary['url'] = None
                    primary['confidence'] = 0.0
                # Reject obvious homepages (no path or just /en, /es, /ca)
                elif not path or path in ['', '/', '/en', '/es', '/ca', '/index.html', '/home']:
                    print(f"  - REJECTED: URL appears to be a homepage (path: '{path}')")
                    primary['url'] = None
                    primary['confidence'] = 0.0
                # Reject very short paths that look like homepages
                elif len(path) < 10 and '?' not in url and not any(x in path for x in ['/noticies/', '/actualitat/', '/premsa/', '/comunicats/', '/nota-de-premsa/', '/salapremsa/', '/notes-premsa/', '/blog/', '/news/', '/press/', '/noticias/', '/novedades/']):
                    print(f"  - REJECTED: URL path too short and not a news/press section ({path})")
                    primary['url'] = None
                    primary['confidence'] = 0.0
                else:
                    print(f"  - ACCEPTED: Valid specific URL (path: {path})")
            else:
                # Fallback: try to extract URLs from raw text (grounded search
                # often mentions URLs in its commentary even with url: null)
                text_urls = re.findall(r'https?://[^\s"\'<>\)]+', raw)
                news_domains_fb = ['bbc.', 'guardian.', 'reuters.', 'cnn.', 'nytimes.',
                                   'elpais.', 'lavanguardia.', 'elperiodico.', 'ara.cat',
                                   'beteve.', 'elnacional.', 'naciodigital.', 'vilaweb.',
                                   '324.cat', 'ccma.cat', 'wikipedia.org']
                fallback_urls = [u for u in text_urls if not any(nd in u.lower() for nd in news_domains_fb)]
                if fallback_urls:
                    print(f"  - Fallback: extracted URL from text: {fallback_urls[0]}")
                    primary['url'] = fallback_urls[0]
                    primary['confidence'] = 0.4
                else:
                    print(f"  - No URL found in search results")
            
            return {
                "primary_source": {
                    "url": primary.get('url'),
                    "title": primary.get('title'),
                    "publisher_guess": primary.get('publisher') or publisher,
                    "type_guess": "official_source",
                    "confidence": float(primary.get('confidence', 0.5)),
                    "source_type": "primary" if primary.get('url') else "news"
                },
                "alternatives": [],
                "reasoning_summary": "Found via Gemini Google Search"
            }
        except json.JSONDecodeError:
            # Try to extract URL from text
            urls = re.findall(r'https?://[^\s"\'<>]+', raw)
            # Filter out news sites
            news_domains = ['bbc.', 'guardian.', 'reuters.', 'cnn.', 'nytimes.', 'washingtonpost.',
                           'elpais.', 'lavanguardia.', 'elperiodico.', 'ara.cat', 'beteve.',
                           'elnacional.', 'naciodigital.', 'vilaweb.', '324.cat', 'ccma.cat']
            valid_urls = [u for u in urls if not any(nd in u.lower() for nd in news_domains)]
            
            if valid_urls:
                return {
                    "primary_source": {
                        "url": valid_urls[0],
                        "title": None,
                        "publisher_guess": publisher,
                        "type_guess": "official_source",
                        "confidence": 0.5,
                        "source_type": "primary"
                    },
                    "alternatives": [],
                    "reasoning_summary": "Extracted from search results"
                }
    except Exception as e:
        print(f"  ⚠️ Source search error: {e}")
    
    # Return empty result
    return {
        "primary_source": {
            "url": None,
            "title": None,
            "publisher_guess": publisher,
            "type_guess": None,
            "confidence": 0.0,
            "source_type": "news"
        },
        "alternatives": [],
        "reasoning_summary": "No primary source found"
    }
