"""Quick Article Creation from URLs, Images, or Text."""
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from io import BytesIO

import requests
from PIL import Image


def extract_text_from_url(url: str) -> dict:
    """Extract text content from a URL."""
    try:
        from bs4 import BeautifulSoup

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else ""

        # Get main content (try common content containers)
        content_selectors = ['article', 'main', '.content', '#content', '.post', '.entry-content']
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                break

        if not content:
            content = soup.find('body')

        # Extract text
        text = content.get_text(separator='\n', strip=True) if content else ""

        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)

        return {
            "source_type": "url",
            "source": url,
            "title": title_text,
            "content": text,
            "raw_html": str(soup)[:5000]  # First 5000 chars of HTML for reference
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


def create_article_json(
    source_type: str,
    content: str,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    additional_context: Optional[str] = None,
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

    # Create article JSON file
    try:
        file_path = create_article_json(
            source_type=extracted_data.get("source_type", "unknown"),
            content=extracted_data.get("content", ""),
            title=extracted_data.get("title"),
            source_url=url,
            additional_context=additional_context,
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
