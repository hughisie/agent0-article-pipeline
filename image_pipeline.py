"""
Image Pipeline Module

Handles downloading, deduplication, and gallery creation for article images.

Features:
  - Downloads images from source URLs
  - Saves images locally per article
  - Perceptual hash deduplication (featured != embedded)
  - Gallery block generation for 3+ unique images
  - WordPress upload integration
"""

import hashlib
import io
import os
import re
import struct
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

# Minimum image size in bytes (30KB) - filter out tiny placeholders/icons
MIN_IMAGE_SIZE_BYTES = 30 * 1024

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}


def _average_hash(image_bytes: bytes, hash_size: int = 8) -> str:
    """
    Compute a simple average hash (aHash) from raw image bytes.
    Returns a binary string of 0s and 1s for Hamming distance comparison.
    Falls back to MD5 of content if image parsing fails.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert('L').resize((hash_size, hash_size))
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        return bits  # Return binary string for Hamming distance
    except ImportError:
        return hashlib.md5(image_bytes).hexdigest()
    except Exception:
        return hashlib.md5(image_bytes).hexdigest()


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hash strings.
    
    For binary strings (perceptual hashes): counts differing bits.
    For hex/md5 strings: returns 999 (incomparable) unless identical.
    """
    if len(hash1) != len(hash2):
        return 999  # Different hash types, can't compare
    # Check if both are binary strings (perceptual hashes)
    if all(c in '01' for c in hash1) and all(c in '01' for c in hash2):
        return sum(a != b for a, b in zip(hash1, hash2))
    # Fallback: exact match only
    return 0 if hash1 == hash2 else 999


def _get_image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    """Get image dimensions (width, height) using PIL."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        return img.size  # (width, height)
    except Exception:
        return None


def detect_and_crop_banner(image_bytes: bytes, max_banner_pct: float = 0.15) -> tuple[bytes, bool]:
    """
    Detect and crop solid-colour banner strips from top/bottom of an image.
    
    Source sites (El Nacional, others) add colored banners (red, yellow) to article images.
    This function detects strips with low colour variance and crops them out.
    
    Args:
        image_bytes: Raw image bytes
        max_banner_pct: Maximum percentage of image height to consider as banner (default 15%)
    
    Returns:
        (cropped_bytes, banner_found) - cropped image bytes and whether a banner was detected
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return image_bytes, False
    
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        width, height = img.size
        
        if width < 100 or height < 100:
            return image_bytes, False
        
        pixels = np.array(img)
        max_banner_rows = int(height * max_banner_pct)
        
        crop_top = 0
        crop_bottom = height
        
        # Check top rows for solid-colour banner
        for row_end in range(min(5, max_banner_rows), max_banner_rows + 1):
            strip = pixels[0:row_end, :, :]
            # Check colour variance across the strip
            # A banner has very low variance (nearly uniform colour)
            r_std = np.std(strip[:, :, 0])
            g_std = np.std(strip[:, :, 1])
            b_std = np.std(strip[:, :, 2])
            avg_std = (r_std + g_std + b_std) / 3
            
            if avg_std < 25:  # Low variance = likely solid banner
                crop_top = row_end
            else:
                break  # Hit photographic content
        
        # Check bottom rows for solid-colour banner
        for row_start in range(height - min(5, max_banner_rows), height - max_banner_rows - 1, -1):
            strip = pixels[row_start:height, :, :]
            r_std = np.std(strip[:, :, 0])
            g_std = np.std(strip[:, :, 1])
            b_std = np.std(strip[:, :, 2])
            avg_std = (r_std + g_std + b_std) / 3
            
            if avg_std < 25:
                crop_bottom = row_start
            else:
                break
        
        # Only crop if we found a significant banner (at least 3% of image height)
        min_banner_height = int(height * 0.03)
        banner_found = (crop_top > min_banner_height) or (height - crop_bottom > min_banner_height)
        
        if banner_found:
            cropped = img.crop((0, crop_top, width, crop_bottom))
            output = io.BytesIO()
            cropped.save(output, 'JPEG', quality=92, optimize=True)
            cropped_bytes = output.getvalue()
            print(f"  🪓 Banner cropped: top={crop_top}px, bottom={height - crop_bottom}px removed")
            return cropped_bytes, True
        
        return image_bytes, False
    
    except Exception as e:
        print(f"  ⚠️ Banner detection failed: {e}")
        return image_bytes, False


def download_image(url: str, timeout: int = 15) -> Optional[bytes]:
    """Download image from URL. Returns bytes or None on failure."""
    if not url or url.startswith("data:"):
        return None
    try:
        response = requests.get(url, timeout=timeout, headers=_BROWSER_HEADERS, allow_redirects=True)
        if response.status_code == 200 and len(response.content) >= MIN_IMAGE_SIZE_BYTES:
            return response.content
        return None
    except requests.RequestException:
        return None


def _filename_from_url(url: str, index: int = 0) -> str:
    """Extract a clean filename from a URL."""
    parsed = urlparse(url)
    name = parsed.path.rsplit("/", 1)[-1]
    # Clean up the filename
    name = re.sub(r'[?#].*$', '', name)
    if not name or '.' not in name:
        name = f"image_{index}.jpg"
    return name


def save_images_locally(
    image_urls: list[str],
    article_path: str,
    article_number: str = "",
) -> list[dict]:
    """
    Download and save images locally alongside the article file.

    Returns list of dicts: {url, local_path, filename, size_bytes, hash}
    """
    article_dir = Path(article_path).parent
    images_dir = article_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, url in enumerate(image_urls):
        data = download_image(url)
        if not data:
            print(f"  ⚠️ Image download failed: {url[:60]}...")
            continue

        # Auto-crop banners (red/yellow strips from El Nacional and other sources)
        data, banner_cropped = detect_and_crop_banner(data)

        filename = _filename_from_url(url, i)
        if article_number:
            filename = f"{article_number}_{filename}"

        local_path = images_dir / filename
        local_path.write_bytes(data)

        img_hash = _average_hash(data)
        dims = _get_image_dimensions(data)
        saved.append({
            "url": url,
            "local_path": str(local_path),
            "filename": filename,
            "size_bytes": len(data),
            "hash": img_hash,
            "_dimensions": dims,
            "data": data,  # Keep in memory for upload
        })
        size_note = f" (banner cropped)" if banner_cropped else ""
        print(f"  📷 Saved image ({len(data) // 1024}KB): {filename}{size_note}")

    return saved


def deduplicate_images(images: list[dict], hamming_threshold: int = 10) -> list[dict]:
    """
    Remove duplicate images using perceptual hashing with Hamming distance.
    
    Two images are considered duplicates if:
    1. Their perceptual hashes have Hamming distance < threshold (same image, different size)
    2. OR they have the same aspect ratio (within 5%) and similar hashes
    
    Returns unique images only, preserving order.
    """
    unique = []
    for img in images:
        h = img.get("hash", "")
        is_duplicate = False
        
        for existing in unique:
            existing_h = existing.get("hash", "")
            
            # Check Hamming distance (works for perceptual hashes)
            dist = _hamming_distance(h, existing_h)
            if dist < hamming_threshold:
                print(f"  🔄 Duplicate image skipped (hamming={dist}): {img.get('filename', '?')}")
                is_duplicate = True
                break
            
            # Secondary check: same aspect ratio + moderately similar hash
            img_dims = img.get("_dimensions")
            existing_dims = existing.get("_dimensions")
            if img_dims and existing_dims:
                img_ratio = img_dims[0] / max(img_dims[1], 1)
                existing_ratio = existing_dims[0] / max(existing_dims[1], 1)
                if abs(img_ratio - existing_ratio) / max(existing_ratio, 0.1) < 0.05:  # Within 5%
                    if dist < hamming_threshold * 2:  # More lenient for same-aspect-ratio
                        print(f"  🔄 Same-ratio duplicate skipped: {img.get('filename', '?')}")
                        is_duplicate = True
                        break
        
        if not is_duplicate:
            unique.append(img)
    
    return unique


def select_featured_and_inline(
    images: list[dict],
) -> tuple[Optional[dict], list[dict]]:
    """
    Select featured image and inline images, ensuring no duplicates.

    Returns:
        (featured_image, inline_images)
        - featured_image: The best image for the featured slot (largest)
        - inline_images: Remaining unique images for embedding/gallery
    """
    if not images:
        return None, []

    unique = deduplicate_images(images)
    if not unique:
        return None, []

    # Sort by size descending - largest = best featured image
    sorted_imgs = sorted(unique, key=lambda x: x.get("size_bytes", 0), reverse=True)

    featured = sorted_imgs[0]
    inline = sorted_imgs[1:]  # Everything except featured

    return featured, inline


def build_gallery_block(image_urls: list[str], alt_text: str = "") -> str:
    """
    Build a WordPress Gutenberg gallery block for 3+ images.

    Args:
        image_urls: List of image URLs (WordPress uploaded URLs preferred)
        alt_text: Default alt text for images

    Returns:
        Gutenberg gallery block HTML
    """
    if len(image_urls) < 2:
        return ""

    # Build individual image items
    items = []
    for url in image_urls:
        items.append(
            f'<figure class="wp-block-image size-large">'
            f'<img src="{url}" alt="{alt_text}" />'
            f'</figure>'
        )

    images_html = "\n".join(items)

    gallery = (
        f'<!-- wp:gallery {{"linkTo":"none","columns":{min(len(image_urls), 3)}}} -->\n'
        f'<figure class="wp-block-gallery has-nested-images columns-{min(len(image_urls), 3)} is-cropped">\n'
        f'{images_html}\n'
        f'</figure>\n'
        f'<!-- /wp:gallery -->\n'
    )
    return gallery


def build_inline_image_block(image_url: str, alt_text: str = "") -> str:
    """Build a single WordPress Gutenberg image block."""
    return (
        '<!-- wp:image {"sizeSlug":"large"} -->\n'
        f'<figure class="wp-block-image size-large">'
        f'<img src="{image_url}" alt="{alt_text}" />'
        f'</figure>\n'
        '<!-- /wp:image -->\n'
    )


def insert_images_into_content(
    content: str,
    inline_images: list[dict],
    alt_text: str = "",
    use_gallery: bool = True,
) -> str:
    """
    Insert inline images or gallery into article content.

    If 1-2 images: insert as individual image blocks after paragraphs
    If 3+: insert as a gallery block

    Args:
        content: Gutenberg block content
        inline_images: List of image dicts with 'uploaded_url' key
        alt_text: Alt text for images
        use_gallery: Whether to use gallery for 3+ images

    Returns:
        Updated content with images inserted
    """
    if not inline_images:
        return content

    urls = [img.get("uploaded_url", img.get("url", "")) for img in inline_images if img.get("uploaded_url") or img.get("url")]
    if not urls:
        return content

    # Find insertion point (after 3rd paragraph, or after promo block)
    from blocks_utils import PROMO_BLOCK, _find_nth_paragraph_end, ensure_spacer_before_image

    if use_gallery and len(urls) >= 3:
        # Gallery mode
        block = build_gallery_block(urls, alt_text)
        insert_after = _find_nth_paragraph_end(content, 4) or _find_nth_paragraph_end(content, 3) or _find_nth_paragraph_end(content, 2)
        if insert_after:
            content, insert_after = ensure_spacer_before_image(content, insert_after)
            return content[:insert_after] + "\n\n" + block + content[insert_after:]
        return content + "\n\n" + block

    elif len(urls) == 1:
        # Single image
        block = build_inline_image_block(urls[0], alt_text)
        insert_after = _find_nth_paragraph_end(content, 3) or _find_nth_paragraph_end(content, 2)
        if insert_after:
            content, insert_after = ensure_spacer_before_image(content, insert_after)
            return content[:insert_after] + "\n\n" + block + content[insert_after:]

    elif len(urls) == 2:
        # Two images - insert at different points
        block1 = build_inline_image_block(urls[0], alt_text)
        insert1 = _find_nth_paragraph_end(content, 3) or _find_nth_paragraph_end(content, 2)
        if insert1:
            content, insert1 = ensure_spacer_before_image(content, insert1)
            content = content[:insert1] + "\n\n" + block1 + content[insert1:]

        block2 = build_inline_image_block(urls[1], alt_text)
        insert2 = _find_nth_paragraph_end(content, 6) or _find_nth_paragraph_end(content, 5)
        if insert2:
            content, insert2 = ensure_spacer_before_image(content, insert2)
            content = content[:insert2] + "\n\n" + block2 + content[insert2:]

    return content
