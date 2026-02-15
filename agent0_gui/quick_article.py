"""Quick Article Creation from URLs, Images, or Text."""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from io import BytesIO

import requests
from PIL import Image


def _extract_meta(soup) -> dict:
    """Extract metadata from HTML head: OG tags, meta description, images."""
    meta = {}
    # OG title
    og_title = soup.find('meta', property='og:title')
    if og_title:
        meta['og_title'] = og_title.get('content', '').strip()
    # OG description
    og_desc = soup.find('meta', property='og:description')
    if og_desc:
        meta['og_description'] = og_desc.get('content', '').strip()
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        meta['meta_description'] = meta_desc.get('content', '').strip()
    # OG image
    og_image = soup.find('meta', property='og:image')
    if og_image:
        meta['og_image'] = og_image.get('content', '').strip()
    # OG site name
    og_site = soup.find('meta', property='og:site_name')
    if og_site:
        meta['og_site_name'] = og_site.get('content', '').strip()
    # Twitter card description
    tw_desc = soup.find('meta', attrs={'name': 'twitter:description'})
    if tw_desc:
        meta['twitter_description'] = tw_desc.get('content', '').strip()
    return meta


def _extract_images_from_html(soup, base_url: str) -> list[str]:
    """Extract image URLs from HTML, filtering out icons and tiny images."""
    from urllib.parse import urljoin
    images = []
    seen = set()
    # OG image first
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        img_url = og_img['content'].strip()
        if img_url not in seen:
            images.append(img_url)
            seen.add(img_url)
    # Then content images
    for img in soup.find_all('img', src=True):
        src = img['src'].strip()
        if src.startswith('data:'):
            continue
        full_url = urljoin(base_url, src)
        # Skip tiny icons/logos
        width = img.get('width', '')
        height = img.get('height', '')
        try:
            if width and int(width) < 50:
                continue
            if height and int(height) < 50:
                continue
        except (ValueError, TypeError):
            pass
        if full_url not in seen:
            images.append(full_url)
            seen.add(full_url)
    return images[:10]  # Max 10 images


def extract_text_from_url(url: str) -> dict:
    """Extract text content, metadata, and images from a URL."""
    try:
        from bs4 import BeautifulSoup

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract metadata before removing elements
        meta = _extract_meta(soup)
        image_urls = _extract_images_from_html(soup, url)

        # Remove script, style, nav, footer, header elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Get title (prefer OG title > HTML title)
        title_text = meta.get('og_title', '')
        if not title_text:
            title = soup.find('title')
            title_text = title.get_text().strip() if title else ""

        # Try progressively broader content selectors
        content_selectors = [
            'article', 'main', '.entry-content', '.post-content',
            '.article-content', '.page-content', '#content', '.content',
            '.post', '.entry', '[role="main"]',
        ]
        content_el = None
        for selector in content_selectors:
            content_el = soup.select_one(selector)
            if content_el and len(content_el.get_text(strip=True)) > 100:
                break
            content_el = None

        if not content_el:
            content_el = soup.find('body')

        # Extract text from content element
        text = content_el.get_text(separator='\n', strip=True) if content_el else ""

        # Also gather all paragraph texts as a fallback
        paragraphs = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 30]
        paragraph_text = '\n\n'.join(paragraphs)

        # Use the longer of the two
        if len(paragraph_text) > len(text):
            text = paragraph_text

        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)

        # Prepend meta description if content is thin
        meta_desc = meta.get('og_description') or meta.get('meta_description') or ''
        if meta_desc and len(text) < 500:
            text = f"{meta_desc}\n\n{text}"

        return {
            "source_type": "url",
            "source": url,
            "title": title_text,
            "content": text,
            "meta": meta,
            "image_urls": image_urls,
            "raw_html": str(soup)[:5000]
        }
    except Exception as e:
        return {
            "source_type": "url",
            "source": url,
            "error": str(e),
            "content": ""
        }


def extract_text_from_image(image_data: bytes) -> dict:
    """Extract text from an image using OCR."""
    try:
        import pytesseract

        # Open image from bytes
        image = Image.open(BytesIO(image_data))

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Perform OCR
        text = pytesseract.image_to_string(image, lang='eng+spa')

        return {
            "source_type": "image",
            "content": text.strip(),
            "image_size": image.size,
            "image_mode": image.mode
        }
    except ImportError:
        return {
            "source_type": "image",
            "error": "pytesseract not installed or tesseract not found",
            "content": "",
            "note": "Install tesseract-ocr system package and pytesseract Python package"
        }
    except Exception as e:
        return {
            "source_type": "image",
            "error": str(e),
            "content": ""
        }


def process_text_input(text: str) -> dict:
    """Process plain text input."""
    return {
        "source_type": "text",
        "content": text.strip()
    }


def research_topic_with_gemini(
    url: str,
    title: str,
    scraped_content: str,
    additional_context: str = "",
    api_key: str = "",
) -> str:
    """Use Gemini with Google Search grounding to research a topic when scraped content is thin."""
    if not api_key:
        from config import load_config
        config = load_config()
        api_key = config.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from llm_clients import GeminiClient

        client = GeminiClient(api_key=api_key, model="gemini-2.5-flash")

        context_hint = f"\nUser context: {additional_context}" if additional_context else ""
        system_prompt = (
            "You are a research assistant. Your job is to gather factual information about a topic "
            "from the web and compile it into a comprehensive briefing document.\n"
            "Write in plain text (not markdown). Include key facts, dates, names, and details.\n"
            "Focus on the most recent and upcoming events/information.\n"
            "Do NOT fabricate information. Only report what you find."
        )
        user_prompt = (
            f"Research the following website and topic thoroughly using web search:\n\n"
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"Scraped content (partial): {scraped_content[:500]}\n"
            f"{context_hint}\n\n"
            f"Please provide a comprehensive factual briefing about this topic including:\n"
            f"- What is this organization/event/project?\n"
            f"- Key dates, locations, and details for the most recent or upcoming edition\n"
            f"- Who organizes it?\n"
            f"- What activities/features does it include?\n"
            f"- Any notable participants, sponsors, or partners\n"
            f"- Historical context (when it started, growth over time)\n"
            f"- Practical info (tickets, venue, schedule)\n\n"
            f"Write a detailed factual briefing (400-800 words)."
        )

        tools = [{"google_search": {}}]
        result = client.generate(system_prompt, user_prompt, tools=tools, timeout=120)
        if result and len(result.strip()) > 100:
            print(f"  ✓ Gemini research returned {len(result)} chars")
            return result.strip()
        return ""
    except Exception as e:
        print(f"  ⚠️ Gemini research failed: {e}")
        return ""


def create_article_json(
    source_type: str,
    content: str,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    additional_context: Optional[str] = None,
    image_urls: Optional[list[str]] = None,
    output_dir: Optional[Path] = None
) -> Path:
    """Create a temporary JSON file for the article pipeline."""

    # Generate timestamp and fingerprint
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    # Extract a headline from title or content
    headline = title if title else content.split('\n')[0][:200]

    # Create article structure
    article_data = {
        "headline": headline,
        "original_title": title or headline,
        "content": content,
        "source_type": source_type,
        "source_url": source_url,
        "additional_context": additional_context,
        "image_urls": image_urls or [],
        "date_time": timestamp,
        "created_at": timestamp,
        "quick_article": True,
        "fingerprint": f"quick_{source_type}_{now.timestamp()}"
    }

    # Use output_dir if provided, otherwise create temp directory
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        target_dir = output_dir
    else:
        temp_dir = Path(tempfile.gettempdir()) / "agent0_quick_articles"
        temp_dir.mkdir(exist_ok=True)
        target_dir = temp_dir

    # Create filename
    safe_headline = re.sub(r'[^a-z0-9]+', '_', headline.lower())[:50]
    filename = f"quick_{safe_headline}_{int(now.timestamp())}.json"
    file_path = target_dir / filename

    # Write JSON file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(article_data, f, indent=2, ensure_ascii=False)

    return file_path


def process_quick_article(
    text: Optional[str] = None,
    url: Optional[str] = None,
    image_data: Optional[bytes] = None,
    additional_context: Optional[str] = None,
    output_dir: Optional[Path] = None
) -> dict:
    """Process a quick article from various input sources."""

    extracted_data = {}

    # Process based on input type
    if url:
        extracted_data = extract_text_from_url(url)
    elif image_data:
        extracted_data = extract_text_from_image(image_data)
    elif text:
        extracted_data = process_text_input(text)
    else:
        return {
            "success": False,
            "error": "No input provided. Please provide text, URL, or image."
        }

    # Check for errors
    if "error" in extracted_data:
        return {
            "success": False,
            "error": extracted_data["error"],
            "details": extracted_data
        }

    content = extracted_data.get("content", "")
    title = extracted_data.get("title", "")
    image_urls = extracted_data.get("image_urls", [])

    # If content is thin (< 500 chars), use Gemini to research the topic
    if url and len(content) < 500:
        print(f"  Content from URL is thin ({len(content)} chars), researching with Gemini...")
        researched = research_topic_with_gemini(
            url=url,
            title=title,
            scraped_content=content,
            additional_context=additional_context or "",
        )
        if researched:
            # Combine: original scraped content + researched content
            content = f"{content}\n\n--- Research from web sources ---\n\n{researched}"
            extracted_data["content"] = content
            extracted_data["gemini_researched"] = True

    # Create article JSON file
    try:
        file_path = create_article_json(
            source_type=extracted_data.get("source_type", "unknown"),
            content=content,
            title=title,
            source_url=url,
            additional_context=additional_context,
            image_urls=image_urls,
            output_dir=output_dir
        )

        return {
            "success": True,
            "file_path": str(file_path),
            "extracted_data": extracted_data,
            "message": f"Quick article created: {file_path.name}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create article JSON: {str(e)}",
            "extracted_data": extracted_data
        }
