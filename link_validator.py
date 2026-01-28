import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from config import load_config
from llm_clients import GeminiSearchClient, LLMError
from url_validator import validate_url


@dataclass(frozen=True)
class AnchorMatch:
    full: str
    href: str
    text: str
    start: int
    end: int


def extract_anchor_matches(content: str) -> list[AnchorMatch]:
    if not content:
        return []
    pattern = re.compile(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    matches = []
    for match in pattern.finditer(content):
        matches.append(
            AnchorMatch(
                full=match.group(0),
                href=match.group(1),
                text=match.group(2),
                start=match.start(),
                end=match.end(),
            )
        )
    return matches


def _check_url(url: str, timeout: int = 15) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers=headers)
        if response.status_code >= 400 or response.status_code == 0:
            response = requests.get(url, allow_redirects=True, timeout=timeout, headers=headers)
        if response.status_code >= 400:
            return False
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "pdf" not in content_type:
            return False
        if response.url and "/not-found" in response.url:
            return False
        text_sample = (response.text or "")[:2000].lower()
        if "404" in text_sample or "not found" in text_sample or "no encontrada" in text_sample:
            return False
        return True
    except requests.RequestException:
        try:
            response = requests.get(url, allow_redirects=True, timeout=timeout, headers=headers)
            if response.status_code >= 400:
                return False
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "pdf" not in content_type:
                return False
            if response.url and "/not-found" in response.url:
                return False
            return True
        except requests.RequestException:
            return False


def _validate_url_with_reason(url: str, timeout: int = 15) -> tuple[bool, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    try:
        head = requests.head(url, allow_redirects=True, timeout=timeout, headers=headers)
        if head.status_code >= 400 or head.status_code == 0:
            result = validate_url(url, timeout=timeout)
            return result.ok, result.reason
    except requests.RequestException:
        result = validate_url(url, timeout=timeout)
        return result.ok, result.reason
    result = validate_url(url, timeout=timeout)
    return result.ok, result.reason


def _replace_href(anchor_html: str, new_url: str) -> str:
    return re.sub(r"href=[\"'][^\"']+[\"']", f'href=\"{new_url}\"', anchor_html, count=1, flags=re.IGNORECASE)


def _extract_first_matching_url(text: str, domain: str) -> Optional[str]:
    """Extract first URL matching domain from text, following redirects if needed."""
    # First try direct match
    pattern = re.compile(rf"https?://{re.escape(domain)}/[^\s\"'<>]+", re.IGNORECASE)
    match = pattern.search(text or "")
    if match:
        return match.group(0)

    # Check for Google/Vertex redirect URLs and follow them
    redirect_pattern = re.compile(r"https?://[^\s\"'<>]*(?:vertexaisearch|google)[^\s\"'<>]*", re.IGNORECASE)
    redirect_match = redirect_pattern.search(text or "")
    if redirect_match:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            response = requests.head(
                redirect_match.group(0),
                allow_redirects=True,
                timeout=10,
                headers=headers,
            )
            final_url = response.url
            if domain in final_url:
                return final_url
        except requests.RequestException:
            pass

    return None


def _build_imet_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    path = parsed.path
    candidates = []
    locales = ["es", "ca", "en"]
    for locale in locales:
        if f"/{locale}/" in path:
            for alt in locales:
                if alt != locale:
                    candidates.append(path.replace(f"/{locale}/", f"/{alt}/", 1))
            candidates.append(path.replace(f"/{locale}/", "/", 1))
        else:
            candidates.append(f"/{locale}{path}")
    if "/web/taxi/" in path:
        candidates.append(path.replace("/web/taxi/", "/taxi/", 1))
        candidates.append(path.replace("/web/taxi/", "/", 1))
        candidates.append(path.replace("/web/taxi/", "/web/imet/", 1))
        candidates.append(path.replace("/web/taxi/", "/imet/", 1))
    candidates.append(path.replace("//", "/"))
    deduped = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return [urlunparse(parsed._replace(path=candidate)) for candidate in deduped]


def _normalize_url_for_compare(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {}
    for key, value in params.items():
        lower = key.lower()
        if lower.startswith("utm_") or lower in {"fbclid", "gclid", "yclid", "igshid"}:
            continue
        cleaned[key] = value
    query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=query))


def _extract_search_terms_from_url(url: str) -> str:
    """Extract meaningful search terms from a URL path."""
    parsed = urlparse(url)
    path = parsed.path

    # Remove file extensions
    path = re.sub(r'\.(aspx|html|htm|php)$', '', path, flags=re.IGNORECASE)

    # Split path into parts and clean
    parts = [p for p in path.split('/') if p and len(p) > 2]

    # Remove common path components
    skip_words = {'paginas', 'pages', 'notasprensa', 'serviciosdeprensa', 'news', 'press', 'web'}
    parts = [p for p in parts if p.lower() not in skip_words]

    # Convert hyphens/underscores to spaces
    terms = ' '.join(parts)
    terms = re.sub(r'[-_]', ' ', terms)

    return terms


def _repair_link(
    url: str,
    search_enabled: bool = True,
    api_keys: dict | None = None,
    anchor_text: str | None = None,
) -> Optional[str]:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Handle taxi.amb.cat specifically
    if "taxi.amb.cat" in domain and "transparencia-y-datos-abiertos" in parsed.path:
        for candidate in _build_imet_candidates(url):
            if _check_url(candidate):
                return candidate
        if search_enabled:
            config = api_keys or load_config()
            api_key = config.get("GEMINI_API_KEY")
            if api_key:
                try:
                    client = GeminiSearchClient(api_key=api_key)
                    query = "site:taxi.amb.cat datos del sector transparencia datos abiertos"
                    result = client.generate(
                        "Find the official taxi.amb.cat page for 'datos del sector' or 'transparencia datos abiertos'.",
                        query,
                    )
                    candidate = _extract_first_matching_url(result, "taxi.amb.cat")
                    if candidate and _check_url(candidate):
                        return candidate
                except LLMError:
                    pass

    # Handle government/official domains - search for correct URL
    official_domains = [
        'lamoncloa.gob.es', 'gob.es', 'gencat.cat', 'govern.cat',
        'ajuntament.barcelona.cat', 'barcelona.cat', 'boe.es',
        'minhafp.gob.es', 'inclusion.gob.es', 'mitma.gob.es',
    ]

    if search_enabled and any(d in domain for d in official_domains):
        config = api_keys or load_config()
        api_key = config.get("GEMINI_API_KEY")
        if api_key:
            try:
                client = GeminiSearchClient(api_key=api_key)

                # Build search query from URL path and anchor text
                search_terms = _extract_search_terms_from_url(url)
                if anchor_text:
                    search_terms = f"{anchor_text} {search_terms}"

                # For govern.cat, try multiple URL patterns
                if "govern.cat" in domain:
                    # govern.cat URLs often have /gov/notes-premsa/ or /salapremsa/notes-premsa/
                    query = f"site:govern.cat notes-premsa {search_terms}"
                else:
                    query = f"site:{domain} {search_terms}"

                result = client.generate(
                    f"Find the exact official page on {domain} that matches this content. "
                    f"The URL MUST be a working page that currently exists. "
                    f"For govern.cat, look in both /gov/notes-premsa/ and /salapremsa/notes-premsa/ paths. "
                    f"Return ONLY the full URL, nothing else. "
                    f"If you cannot find a matching page, respond with 'NOT_FOUND'.",
                    f"Search: {query}",
                )

                # Extract URL from response
                if result and "NOT_FOUND" not in result.upper():
                    candidate = _extract_first_matching_url(result, domain)
                    if candidate and _check_url(candidate):
                        return candidate
            except LLMError:
                pass

    return None


def _is_generic_homepage_url(url: str, anchor_text: str = "") -> bool:
    """Check if a URL is a generic homepage without specific content."""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')

    # Check if it's just a domain with no path or only index page
    if not path or path in ['', '/', '/index.html', '/index.php', '/home', '/en', '/es', '/ca']:
        # Allow whatsapp.com/channel/ URLs (specific content)
        if 'whatsapp.com' in parsed.netloc and '/channel/' in url:
            return False

        # Check anchor text for generic patterns
        generic_patterns = [
            r'for more information',
            r'visit.*website',
            r'official.*site',
            r'read more',
            r'learn more',
            r'find out more',
            r'more details',
            r'click here',
        ]

        anchor_lower = anchor_text.lower()
        for pattern in generic_patterns:
            if re.search(pattern, anchor_lower):
                return True

        # These are generic homepage links
        return True

    # Check for common homepage-only paths
    homepage_paths = ['/about', '/contact', '/about-us', '/contacto', '/qui-som', '/quienes-somos']
    if path in homepage_paths:
        return True

    return False


def _is_likely_fabricated_social_url(url: str) -> bool:
    """Check if a social media URL is likely fabricated (wrong format or placeholder IDs)."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path

    # Check for Twitter/X URLs
    if domain in ['twitter.com', 'x.com', 'www.twitter.com', 'www.x.com']:
        # Check for suspicious status ID patterns
        status_match = re.search(r'/status/(\d+)', path)
        if status_match:
            status_id = status_match.group(1)
            # Twitter IDs created after 2006 are > 10^17, most are > 10^18
            # IDs that look made up often have wrong patterns
            if len(status_id) < 15:  # Too short to be a real recent tweet
                return True
            # Check for placeholder-like IDs
            if re.match(r'^[01]+$', status_id) or 'XXXXX' in status_id:
                return True
        else:
            # No valid status pattern - might be missing path
            if '/status/' not in path and path.count('/') < 2:
                return True

    # Check for Instagram URLs
    if domain in ['instagram.com', 'www.instagram.com']:
        if '/p/' in path:
            # Instagram shortcodes are 11 characters of base64
            code_match = re.search(r'/p/([^/]+)', path)
            if code_match:
                code = code_match.group(1)
                if len(code) < 8:  # Too short
                    return True

    return False


def validate_and_fix_links_in_content(
    content: str,
    search_enabled: bool = True,
    api_keys: dict | None = None,
) -> tuple[str, dict]:
    matches = extract_anchor_matches(content)
    report = {
        "total_links": len(matches),
        "broken_links": 0,
        "replaced_links": 0,
        "unlinked_links": 0,
        "actions": [],
    }
    if api_keys is not None and not api_keys.get("VALIDATE_OUTBOUND_URLS", True):
        report["skipped"] = True
        return content, report
    if not matches:
        return content, report

    updated = content
    for match in reversed(matches):
        href = match.href.strip()
        if not href:
            continue
        if "barna.news" in href:
            continue
        if _check_url(href):
            continue
        report["broken_links"] += 1
        replacement = _repair_link(href, search_enabled=search_enabled, api_keys=api_keys)
        if replacement:
            new_anchor = _replace_href(match.full, replacement)
            updated = updated[:match.start] + new_anchor + updated[match.end:]
            report["replaced_links"] += 1
            report["actions"].append({"href": href, "action": "replaced", "replacement": replacement})
        else:
            updated = updated[:match.start] + match.text + updated[match.end:]
            report["unlinked_links"] += 1
            report["actions"].append({"href": href, "action": "unlinked"})
    return updated, report


def validate_and_delink_outbound_links(
    content: str,
    enabled: bool = True,
    internal_domain: str = "barna.news",
    allowed_urls: set[str] | None = None,
    allowed_domains: set[str] | None = None,
    repair_enabled: bool = True,
    api_keys: dict | None = None,
) -> tuple[str, dict]:
    report = {
        "enabled": bool(enabled),
        "repair_enabled": bool(repair_enabled),
        "checked": 0,
        "broken": 0,
        "repaired": 0,
        "removed_links": [],
        "repaired_links": [],
        "kept_links": [],
    }
    if not enabled:
        return content, report
    matches = extract_anchor_matches(content)
    if not matches:
        return content, report
    allowed_urls = {url.strip() for url in (allowed_urls or set()) if url and url.strip()}
    allowed_normalized = {_normalize_url_for_compare(url) for url in allowed_urls}
    allowed_domains = {domain.strip().lower() for domain in (allowed_domains or set()) if domain and domain.strip()}
    updated = content
    for match in reversed(matches):
        href = match.href.strip()
        if not href or not href.startswith(("http://", "https://")):
            continue
        if href in allowed_urls or _normalize_url_for_compare(href) in allowed_normalized:
            report["checked"] += 1
            report["kept_links"].append({"url": href})
            continue
        parsed = urlparse(href)
        domain = parsed.netloc.lower()
        if allowed_domains and domain in allowed_domains:
            report["checked"] += 1
            report["kept_links"].append({"url": href})
            continue
        if internal_domain and internal_domain in href:
            continue

        # Check for generic homepage URLs and remove immediately
        if _is_generic_homepage_url(href, match.text):
            report["checked"] += 1
            report["broken"] += 1
            updated = updated[:match.start] + match.text + updated[match.end:]
            report["removed_links"].append({"url": href, "reason": "generic homepage URL without specific content"})
            continue

        # Check for likely fabricated social media URLs and remove immediately
        if _is_likely_fabricated_social_url(href):
            report["checked"] += 1
            report["broken"] += 1
            updated = updated[:match.start] + match.text + updated[match.end:]
            report["removed_links"].append({"url": href, "reason": "likely fabricated social media URL"})
            continue

        report["checked"] += 1
        ok, reason = _validate_url_with_reason(href)
        if ok:
            report["kept_links"].append({"url": href})
            continue

        # Try to repair the link before delinking
        if repair_enabled:
            repaired_url = _repair_link(
                href,
                search_enabled=True,
                api_keys=api_keys,
                anchor_text=match.text,
            )
            if repaired_url:
                # Replace the broken URL with the repaired one
                new_anchor = _replace_href(match.full, repaired_url)
                updated = updated[:match.start] + new_anchor + updated[match.end:]
                report["repaired"] += 1
                report["repaired_links"].append({
                    "original_url": href,
                    "repaired_url": repaired_url,
                    "reason": reason,
                })
                continue

        # Delink if repair failed
        report["broken"] += 1
        updated = updated[:match.start] + match.text + updated[match.end:]
        report["removed_links"].append({"url": href, "reason": reason})
    return updated, report
