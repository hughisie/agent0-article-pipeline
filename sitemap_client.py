import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests


class SitemapError(Exception):
    pass


def _fetch_xml(url: str, timeout: int = 30) -> ET.Element:
    response = requests.get(url, timeout=timeout)
    if response.status_code != 200:
        raise SitemapError(f"Failed to fetch sitemap: {response.status_code} {response.text}")
    return ET.fromstring(response.text)


def _extract_locs(root: ET.Element) -> list[str]:
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = []
    for loc in root.findall(".//sm:loc", ns):
        if loc.text:
            locs.append(loc.text.strip())
    return locs


def fetch_post_urls_from_sitemap(base_sitemap_url: str, max_urls: int = 500) -> list[str]:
    root = _fetch_xml(base_sitemap_url)
    tag = root.tag.lower()
    urls = []
    if tag.endswith("sitemapindex"):
        sitemap_urls = [
            loc
            for loc in _extract_locs(root)
            if "post" in loc and "category" not in loc and "page" not in loc
        ]
        for sitemap_url in sitemap_urls:
            child_root = _fetch_xml(sitemap_url)
            urls.extend(_extract_locs(child_root))
            if len(urls) >= max_urls:
                break
    else:
        urls = _extract_locs(root)
    return urls[:max_urls]


def filter_urls_by_category(urls: list[str], category_slug: str | None, category_name: str | None) -> list[str]:
    if not urls:
        return []
    slug = (category_slug or "").strip().lower()
    name = (category_name or "").strip().lower()
    tokens = {t for t in [slug, name] if t}
    if not tokens:
        return urls
    filtered = []
    for url in urls:
        path = urlparse(url).path.lower()
        if any(token in path for token in tokens):
            filtered.append(url)
    return filtered
