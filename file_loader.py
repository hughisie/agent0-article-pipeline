import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


@dataclass
class Article:
    title: Optional[str] = None
    original_title: Optional[str] = None
    original_language: Optional[str] = None
    main_content_body: str = ""
    date_time: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    source_url_base: Optional[str] = None
    image_urls: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    external_references: list[dict] = field(default_factory=list)  # Social media posts and external links
    profile_name: Optional[str] = None
    primary_source_url: Optional[str] = None  # Primary source URL if provided in metadata

    def to_dict(self) -> dict:
        return asdict(self)


SUPPORTED_SUFFIXES = {".json", ".md", ".markdown"}


def load_article(path: str) -> Article:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Unsupported file type. Use .json or .md")

    if file_path.suffix.lower() == ".json":
        return _load_from_json(file_path)
    return _load_from_markdown(file_path)


def _load_from_json(path: Path) -> Article:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}")

    # Support both standard format and quick_article format
    title = raw.get("title") or raw.get("headline")
    original_title = raw.get("original_title") or raw.get("headline")
    main_content_body = raw.get("main_content_body") or raw.get("content", "") or ""

    # Get external_references (list of dicts)
    external_refs = raw.get("external_references", [])
    if not isinstance(external_refs, list):
        external_refs = []

    # Get primary_source_url if provided
    primary_source_url = raw.get("primary_source_url") or raw.get("primary_source")
    if primary_source_url and _is_valid_url(primary_source_url):
        pass  # URL is valid
    else:
        primary_source_url = None

    return Article(
        title=title,
        original_title=original_title,
        original_language=raw.get("original_language"),
        main_content_body=main_content_body,
        date_time=raw.get("date_time"),
        source_url=raw.get("source_url"),
        source_name=raw.get("source_name"),
        source_url_base=raw.get("source_url_base"),
        image_urls=_normalize_keywords(raw.get("image_urls")),
        keywords=_normalize_keywords(raw.get("keywords")),
        external_references=external_refs,
        profile_name=raw.get("profile_name"),
        primary_source_url=primary_source_url,
    )


def _load_from_markdown(path: Path) -> Article:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(text)

    title = meta.get("title") or path.stem
    # Support multiple date field names
    date_time = meta.get("date") or meta.get("date_time") or meta.get("published")
    source_url = meta.get("source_url") or meta.get("url")
    source_name = meta.get("source_name") or meta.get("source")
    keywords = _normalize_keywords(meta.get("keywords"))

    # Extract source_url_base from source_url if not provided
    source_url_base = meta.get("source_url_base")
    if not source_url_base and source_url:
        parsed = urlparse(source_url)
        source_url_base = f"{parsed.scheme}://{parsed.netloc}"

    # Extract original_title if not provided (use title from metadata)
    original_title = meta.get("original_title") or title

    # Extract image URLs from HTML content
    image_urls = _normalize_keywords(meta.get("image_urls"))
    if not image_urls:
        image_urls = _extract_image_urls_from_html(body)

    # Clean HTML tags from body for plain text content
    clean_body = _strip_html_tags(body).strip()

    # Get primary_source_url if provided and validate it
    primary_source_url = meta.get("primary_source_url") or meta.get("primary_source") or meta.get("original_source_url")
    if primary_source_url and _is_valid_url(primary_source_url):
        pass  # URL is valid
    else:
        primary_source_url = None

    return Article(
        title=title,
        original_title=original_title,
        original_language=meta.get("original_language"),
        main_content_body=clean_body,
        date_time=date_time,
        source_url=source_url,
        source_name=source_name,
        source_url_base=source_url_base,
        image_urls=image_urls,
        keywords=keywords,
        profile_name=meta.get("profile_name"),
        primary_source_url=primary_source_url,
    )


def _parse_front_matter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if len(lines) >= 3 and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                meta_lines = lines[1:idx]
                body = "\n".join(lines[idx + 1 :])
                return _parse_meta_lines(meta_lines), body
    return {}, text


def _parse_meta_lines(lines: list[str]) -> dict:
    meta = {}
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def _normalize_keywords(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"\'') for item in inner.split(",") if item.strip()]
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


def _extract_image_urls_from_html(html: str) -> list[str]:
    """Extract image URLs from HTML content."""
    # Find all <img> tags and extract src attributes
    img_pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
    urls = re.findall(img_pattern, html, re.IGNORECASE)
    # Deduplicate and filter out data URIs
    seen = set()
    result = []
    for url in urls:
        url = url.strip()
        if url and not url.startswith('data:') and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _strip_html_tags(html: str) -> str:
    """Remove HTML tags and decode entities for plain text content."""
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Replace <br>, </p>, </div>, </li> with newlines to preserve some structure
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</p>', '\n\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</div>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</li>', '\n', html, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode common HTML entities
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&amp;', '&')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&quot;', '"')
    html = html.replace('&#8217;', "'")
    html = html.replace('&#8220;', '"')
    html = html.replace('&#8221;', '"')

    # Clean up excessive whitespace
    html = re.sub(r'\n\s*\n\s*\n+', '\n\n', html)  # Multiple newlines to double newline
    html = re.sub(r' +', ' ', html)  # Multiple spaces to single space

    return html.strip()


def _is_valid_url(url: str) -> bool:
    """Check if a URL is well-formed."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in ('http', 'https') and parsed.netloc)
    except Exception:
        return False
