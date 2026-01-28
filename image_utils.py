import re
from urllib.parse import urlparse


def _normalise_url_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value.strip()]
    return []


def extract_image_urls_from_article(article: dict, raw_markdown: str | None = None) -> list[str]:
    urls = []
    for key in ["image_urls", "image_url", "featured_image", "cover_image", "image", "imageUrl"]:
        urls.extend(_normalise_url_list(article.get(key)))

    if raw_markdown:
        matches = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", raw_markdown)
        urls.extend([match.strip() for match in matches if match.strip()])

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def extract_image_url_from_article(article: dict, raw_markdown: str | None = None) -> str | None:
    urls = extract_image_urls_from_article(article, raw_markdown)
    return urls[0] if urls else None


def build_alt_text(primary_keyword: str | None, core_topic: str | None) -> str:
    parts = [value for value in [primary_keyword, core_topic] if value]
    if not parts:
        return "News story image"
    text = " - ".join(parts)
    return text[:120]


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = parsed.path.rsplit("/", 1)[-1]
    return name or "image.jpg"
