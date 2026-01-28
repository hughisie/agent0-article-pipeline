"""Enhanced primary source validation to prevent incorrect URL embedding."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class SourceValidation:
    """Result of primary source validation."""
    url: str
    is_valid: bool
    status_code: Optional[int]
    content_match_score: float
    title_match_score: float
    issues: list[str]
    warnings: list[str]
    extracted_title: Optional[str]
    extracted_date: Optional[str]


def _extract_text_content(html: str) -> str:
    """Extract clean text from HTML."""
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator=' ', strip=True)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text[:8000]  # First 8000 chars for better detection
    except Exception:
        return ""


def _extract_article_metadata(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract title and date from HTML."""
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Try to find title
        title = None
        title_tag = soup.find('h1')
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif soup.find('title'):
            title = soup.find('title').get_text(strip=True)

        # Try to find date
        date = None
        # Common date meta tags
        date_metas = [
            ('property', 'article:published_time'),
            ('name', 'publish_date'),
            ('name', 'date'),
            ('property', 'og:updated_time'),
        ]
        for attr, value in date_metas:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                date = meta.get('content')
                break

        return title, date
    except Exception:
        return None, None


def _similarity_score(text1: str, text2: str) -> float:
    """Calculate similarity between two texts (0-1)."""
    if not text1 or not text2:
        return 0.0

    # Normalize
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()

    # Use SequenceMatcher
    return SequenceMatcher(None, text1, text2).ratio()


def _extract_key_terms(text: str) -> set[str]:
    """Extract key terms from text for matching."""
    # Remove common words and extract meaningful terms
    words = re.findall(r'\b[a-zàèéíòóúçñ]{4,}\b', text.lower())

    # Filter out common Spanish/Catalan words
    common_words = {
        'para', 'este', 'esta', 'desde', 'hasta', 'como', 'pero', 'porque',
        'sobre', 'entre', 'contra', 'todas', 'estos', 'estas', 'otros',
        'mateix', 'aquest', 'aquesta', 'tots', 'totes', 'altres', 'entre'
    }

    return {w for w in words if w not in common_words}[:50]


def validate_primary_source_url(
    url: str,
    article_title: str,
    article_content: str,
    expected_keywords: Optional[list[str]] = None,
    timeout: int = 15
) -> SourceValidation:
    """
    Validate that a primary source URL actually matches the article content.

    Args:
        url: Primary source URL to validate
        article_title: Title of the article being written
        article_content: Content/summary of the article
        expected_keywords: List of keywords that should appear in the source
        timeout: Request timeout in seconds

    Returns:
        SourceValidation with detailed results
    """
    issues = []
    warnings = []

    # Parse URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            issues.append("Invalid URL format")
            return SourceValidation(
                url=url,
                is_valid=False,
                status_code=None,
                content_match_score=0.0,
                title_match_score=0.0,
                issues=issues,
                warnings=warnings,
                extracted_title=None,
                extracted_date=None
            )
    except Exception as e:
        issues.append(f"URL parsing error: {str(e)}")
        return SourceValidation(
            url=url,
            is_valid=False,
            status_code=None,
            content_match_score=0.0,
            title_match_score=0.0,
            issues=issues,
            warnings=warnings,
            extracted_title=None,
            extracted_date=None
        )

    # Fetch URL
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        status_code = response.status_code

        if status_code >= 400:
            # Special handling for social media authentication errors
            domain = parsed.netloc.lower()
            if status_code in (401, 403) and any(sm in domain for sm in ['twitter.com', 'x.com', 'facebook.com', 'instagram.com']):
                issues.append(f"Social media URL blocked (HTTP {status_code}) - requires authentication or unavailable")
                issues.append("Recommend finding official press release instead of social media post")
            else:
                issues.append(f"HTTP {status_code} error")
            return SourceValidation(
                url=url,
                is_valid=False,
                status_code=status_code,
                content_match_score=0.0,
                title_match_score=0.0,
                issues=issues,
                warnings=warnings,
                extracted_title=None,
                extracted_date=None
            )

        # Check for redirects to different articles
        if response.url != url:
            original_path = parsed.path
            final_path = urlparse(response.url).path

            # Extract ID numbers from paths
            original_ids = re.findall(r'/(\d{5,})', original_path)
            final_ids = re.findall(r'/(\d{5,})', final_path)

            if original_ids and final_ids and original_ids != final_ids:
                warnings.append(f"URL redirected to different article ID: {original_ids[0]} -> {final_ids[0]}")

        html = response.text

        # Extract metadata
        extracted_title, extracted_date = _extract_article_metadata(html)

        # Extract content
        source_content = _extract_text_content(html)

        if not source_content:
            issues.append("No extractable content from source")
            return SourceValidation(
                url=url,
                is_valid=False,
                status_code=status_code,
                content_match_score=0.0,
                title_match_score=0.0,
                issues=issues,
                warnings=warnings,
                extracted_title=extracted_title,
                extracted_date=extracted_date
            )

        # Check for error pages and unpublished articles
        error_indicators = [
            '404', 'not found', 'no encontrada', 'error',
            'article no longer available', 'artículo no disponible',
            'unpublished', 'removed', 'deleted', 'no longer exists',
            'la noticia ya no está disponible', 'ha sido despublicada',
            'content has been removed', 'page not found'
        ]
        content_lower = source_content.lower()
        for indicator in error_indicators:
            if indicator in content_lower[:1000]:
                issues.append(f"Source shows error/unavailable message: '{indicator}'")
                break
        
        # Check for homepage/generic pages
        homepage_indicators = [
            '/home', '/index', '/about', '/associacio', '/asociacion',
            '/contact', '/contacte', '/contacto', '/qui-som', '/quienes-somos',
            '/about-us', '/home.html', '/index.html', '/default.aspx'
        ]
        url_lower = url.lower()
        path_only = urlparse(url).path.lower()
        
        # Check if URL ends with homepage patterns or is just a domain
        if path_only in ['/', ''] or any(path_only.endswith(pattern) or pattern in path_only for pattern in homepage_indicators):
            issues.append("URL appears to be homepage or generic about/association page, not a specific document")
        
        # Check if content length is very short (likely navigation page)
        if len(source_content) < 200:
            warnings.append("Very short content - may be navigation/index page rather than full document")

        # Calculate title similarity
        title_match_score = 0.0
        if extracted_title and article_title:
            title_match_score = _similarity_score(extracted_title, article_title)
            if title_match_score < 0.3:
                warnings.append(f"Title mismatch (score: {title_match_score:.2f})")

        # Calculate content similarity
        article_terms = _extract_key_terms(article_content)
        source_terms = _extract_key_terms(source_content)

        if article_terms and source_terms:
            common_terms = article_terms & source_terms
            content_match_score = len(common_terms) / max(len(article_terms), len(source_terms))
        else:
            content_match_score = 0.0

        if content_match_score < 0.2:
            warnings.append(f"Low content match (score: {content_match_score:.2f})")

        # Check expected keywords
        if expected_keywords:
            source_lower = source_content.lower()
            missing_keywords = [kw for kw in expected_keywords if kw.lower() not in source_lower]
            if missing_keywords:
                warnings.append(f"Missing expected keywords: {', '.join(missing_keywords[:3])}")

        # Determine if valid
        is_valid = (
            status_code == 200
            and not issues
            and (content_match_score >= 0.2 or title_match_score >= 0.4)
        )

        return SourceValidation(
            url=url,
            is_valid=is_valid,
            status_code=status_code,
            content_match_score=content_match_score,
            title_match_score=title_match_score,
            issues=issues,
            warnings=warnings,
            extracted_title=extracted_title,
            extracted_date=extracted_date
        )

    except requests.RequestException as e:
        issues.append(f"Request failed: {str(e)}")
        return SourceValidation(
            url=url,
            is_valid=False,
            status_code=None,
            content_match_score=0.0,
            title_match_score=0.0,
            issues=issues,
            warnings=warnings,
            extracted_title=None,
            extracted_date=None
        )
    except Exception as e:
        issues.append(f"Validation error: {str(e)}")
        return SourceValidation(
            url=url,
            is_valid=False,
            status_code=None,
            content_match_score=0.0,
            title_match_score=0.0,
            issues=issues,
            warnings=warnings,
            extracted_title=None,
            extracted_date=None
        )


def compare_similar_urls(url1: str, url2: str, article_title: str, article_content: str) -> str:
    """
    Compare two similar URLs and return the better match.

    Useful when you have URLs with same slug but different IDs.
    """
    result1 = validate_primary_source_url(url1, article_title, article_content)
    result2 = validate_primary_source_url(url2, article_title, article_content)

    # Prefer valid over invalid
    if result1.is_valid and not result2.is_valid:
        return url1
    if result2.is_valid and not result1.is_valid:
        return url2

    # Compare match scores
    score1 = (result1.content_match_score + result1.title_match_score) / 2
    score2 = (result2.content_match_score + result2.title_match_score) / 2

    return url1 if score1 >= score2 else url2
