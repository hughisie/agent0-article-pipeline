import base64
import json
import mimetypes
import re
from datetime import datetime, timedelta
from html import unescape
from typing import Optional
from urllib.parse import urlparse

import requests

_CACHED_CATEGORIES = None
_CACHED_TAGS = None


class WordPressError(Exception):
    pass


def _basic_auth_header(username: str, application_password: str) -> dict:
    token = f"{username}:{application_password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(token).decode("ascii")}


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return unescape(text)


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_recent_posts(
    base_url: str,
    username: str,
    application_password: str,
    months_back: int = 3,
    max_posts: int = 50,
) -> list[dict]:
    headers = _basic_auth_header(username, application_password)
    categories = get_wp_categories(base_url, username, application_password)
    tags = get_wp_tags(base_url, username, application_password)
    category_map = {item.get("id"): item.get("name") for item in categories or []}
    tag_map = {item.get("id"): item.get("name") for item in tags or []}
    posts = []
    page = 1
    per_page = min(100, max_posts)
    cutoff = datetime.now() - timedelta(days=30 * months_back)

    while len(posts) < max_posts:
        params = {
            "per_page": per_page,
            "page": page,
            "status": "publish",
            "orderby": "date",
            "order": "desc",
        }
        url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 400 and "rest_post_invalid_page_number" in response.text:
            break
        if response.status_code != 200:
            raise WordPressError(f"Failed to fetch posts: {response.status_code} {response.text}")
        data = response.json()
        if not data:
            break

        for item in data:
            post_date = _parse_date(item.get("date"))
            if post_date and post_date < cutoff:
                continue
            excerpt = _strip_html(item.get("excerpt", {}).get("rendered", ""))
            content = _strip_html(item.get("content", {}).get("rendered", ""))
            snippet = " ".join(content.split(" ")[:80]).strip()
            category_ids = item.get("categories") or []
            tag_ids = item.get("tags") or []
            posts.append(
                {
                    "id": item.get("id"),
                    "title": _strip_html(item.get("title", {}).get("rendered", "")),
                    "url": item.get("link"),
                    "date": item.get("date"),
                    "excerpt": excerpt,
                    "content_snippet": snippet,
                    "categories": [category_map.get(cat_id) for cat_id in category_ids if category_map.get(cat_id)],
                    "tags": [tag_map.get(tag_id) for tag_id in tag_ids if tag_map.get(tag_id)],
                }
            )
            if len(posts) >= max_posts:
                break
        page += 1

    return posts


def get_additional_posts_for_continuations(
    base_url: str,
    username: str,
    application_password: str,
    max_posts: int = 100,
) -> list[dict]:
    headers = _basic_auth_header(username, application_password)
    posts = []
    page = 1
    per_page = min(100, max_posts)

    while len(posts) < max_posts:
        params = {"per_page": per_page, "page": page}
        url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 400 and "rest_post_invalid_page_number" in response.text:
            break
        if response.status_code != 200:
            raise WordPressError(f"Failed to fetch posts: {response.status_code} {response.text}")
        data = response.json()
        if not data:
            break
        for item in data:
            excerpt = _strip_html(item.get("excerpt", {}).get("rendered", ""))
            content = _strip_html(item.get("content", {}).get("rendered", ""))
            snippet = " ".join(content.split(" ")[:80]).strip()
            posts.append(
                {
                    "id": item.get("id"),
                    "title": _strip_html(item.get("title", {}).get("rendered", "")),
                    "url": item.get("link"),
                    "date": item.get("date"),
                    "excerpt": excerpt,
                    "content_snippet": snippet,
                    "categories": [],
                    "tags": [],
                }
            )
            if len(posts) >= max_posts:
                break
        page += 1

    return posts


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if not path:
        return ""
    return path.split("/")[-1]


def get_posts_by_urls(
    base_url: str,
    username: str,
    application_password: str,
    urls: list[str],
    max_posts: int = 120,
) -> list[dict]:
    if not urls:
        return []
    headers = _basic_auth_header(username, application_password)
    categories = get_wp_categories(base_url, username, application_password)
    tags = get_wp_tags(base_url, username, application_password)
    category_map = {item.get("id"): item.get("name") for item in categories or []}
    tag_map = {item.get("id"): item.get("name") for item in tags or []}
    posts = []
    seen = set()
    for url in urls:
        if len(posts) >= max_posts:
            break
        slug = _slug_from_url(url)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        params = {"slug": slug, "status": "publish"}
        api_url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            continue
        data = response.json()
        if not data:
            continue
        item = data[0]
        excerpt = _strip_html(item.get("excerpt", {}).get("rendered", ""))
        content = _strip_html(item.get("content", {}).get("rendered", ""))
        snippet = " ".join(content.split(" ")[:80]).strip()
        category_ids = item.get("categories") or []
        tag_ids = item.get("tags") or []
        posts.append(
            {
                "id": item.get("id"),
                "title": _strip_html(item.get("title", {}).get("rendered", "")),
                "url": item.get("link"),
                "date": item.get("date"),
                "excerpt": excerpt,
                "content_snippet": snippet,
                "categories": [category_map.get(cat_id) for cat_id in category_ids if category_map.get(cat_id)],
                "tags": [tag_map.get(tag_id) for tag_id in tag_ids if tag_map.get(tag_id)],
            }
        )
    return posts


def upload_media_from_url(
    base_url: str,
    username: str,
    application_password: str,
    image_url: str,
    alt_text: Optional[str] = None,
) -> int:
    from PIL import Image
    from io import BytesIO

    # Try to enable AVIF support (optional)
    try:
        import pillow_avif
        print("AVIF support enabled via pillow_avif")
    except ImportError:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            print("AVIF support enabled via pillow_heif")
        except ImportError:
            print("Warning: AVIF support not available, may fail on AVIF images")

    # Skip base64 data URI images (they cause InvalidSchema errors)
    if image_url.startswith('data:'):
        print(f"Skipping base64 data URI image (not a downloadable URL)")
        return None, None
    
    download = requests.get(image_url, stream=True, timeout=60)
    if download.status_code != 200:
        raise WordPressError(f"Failed to download image: {download.status_code}")

    parsed = urlparse(image_url)
    original_filename = parsed.path.rsplit("/", 1)[-1] or "image.jpg"

    # Convert AVIF/WebP to JPG for better compatibility with social media (X/Twitter cards)
    print(f"Converting image from {original_filename} to JPG format...")
    try:
        img = Image.open(BytesIO(download.content))
        print(f"Image opened successfully. Format: {img.format}, Mode: {img.mode}, Size: {img.size}")

        # Convert to RGB if needed (for JPG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Convert to JPG
        output = BytesIO()
        img.save(output, 'JPEG', quality=90, optimize=True)
        image_data = output.getvalue()
        file_size_bytes = len(image_data)
        file_size_kb = file_size_bytes / 1024
        print(f"Image converted to JPG successfully. Size: {file_size_bytes} bytes ({file_size_kb:.1f} KB)")
        
        # Skip images smaller than 50KB (likely thumbnails/icons)
        MIN_SIZE_KB = 50
        if file_size_kb < MIN_SIZE_KB:
            print(f"⚠️  Skipping small image ({file_size_kb:.1f} KB < {MIN_SIZE_KB} KB minimum) - likely a thumbnail or icon")
            return None, None

        # Update filename to .jpg
        filename = re.sub(r'\.(avif|webp|png)$', '.jpg', original_filename, flags=re.IGNORECASE)
        if not filename.endswith('.jpg'):
            filename = filename.rsplit('.', 1)[0] + '.jpg' if '.' in filename else filename + '.jpg'

        content_type = "image/jpeg"
        print(f"Uploading as: {filename} (Content-Type: {content_type})")

    except Exception as e:
        # If conversion fails, use original
        print(f"ERROR: Image conversion failed, using original format: {e}")
        import traceback
        traceback.print_exc()
        image_data = download.content
        filename = original_filename
        content_type = download.headers.get("Content-Type")
        if not content_type:
            guessed, _ = mimetypes.guess_type(filename)
            content_type = guessed or "image/jpeg"

    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
        "Content-Type": content_type,
    }
    headers.update(_basic_auth_header(username, application_password))
    media_url = f"{base_url.rstrip('/')}/wp-json/wp/v2/media"
    response = requests.post(media_url, headers=headers, data=image_data, timeout=60)
    if response.status_code not in {200, 201}:
        raise WordPressError(f"Failed to upload media: {response.status_code} {response.text}")

    response_data = response.json()
    media_id = response_data.get("id")
    if not media_id:
        raise WordPressError("Media upload did not return an ID")

    # Get the source URL for social media metadata
    source_url = response_data.get("source_url")
    print(f"WordPress assigned URL: {source_url}")

    # If WordPress kept the AVIF extension despite our JPG upload, warn about it
    if source_url and source_url.endswith('.avif'):
        print(f"WARNING: WordPress saved image as .avif despite JPG upload. This may cause Twitter/X card issues.")

    if alt_text:
        update_url = f"{base_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
        update_headers = {"Content-Type": "application/json"}
        update_headers.update(_basic_auth_header(username, application_password))
        update_payload = json.dumps({"alt_text": alt_text})
        update_resp = requests.post(update_url, headers=update_headers, data=update_payload, timeout=30)
        if update_resp.status_code not in {200, 201}:
            raise WordPressError(f"Failed to set alt text: {update_resp.status_code} {update_resp.text}")

    return int(media_id), source_url


def create_draft_post(
    base_url: str,
    username: str,
    application_password: str,
    meta: dict,
    media_id: Optional[int] = None,
    author_id: Optional[int] = None,
) -> dict:
    payload = {
        "title": meta.get("meta_title"),
        "content": meta.get("wp_block_content") or meta.get("wp_html_content"),
        "excerpt": meta.get("excerpt"),
        "status": "draft",
        "slug": meta.get("slug"),
    }
    if media_id is not None:
        payload["featured_media"] = media_id
    if author_id is not None:
        payload["author"] = author_id

    category_id = meta.get("category_id")
    if category_id:
        payload["categories"] = [category_id]
    tag_ids = meta.get("tag_ids") or []
    if tag_ids:
        payload["tags"] = tag_ids

    headers = {"Content-Type": "application/json"}
    headers.update(_basic_auth_header(username, application_password))
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code not in {200, 201}:
        raise WordPressError(f"Failed to create draft: {response.status_code} {response.text}")

    return response.json()

def update_post(
    base_url: str,
    username: str,
    application_password: str,
    post_id: int,
    meta: dict,
    media_id: Optional[int] = None,
    author_id: Optional[int] = None,
) -> dict:
    payload = {
        "title": meta.get("meta_title"),
        "content": meta.get("wp_block_content") or meta.get("wp_html_content"),
        "excerpt": meta.get("excerpt"),
        "slug": meta.get("slug"),
    }
    if media_id is not None:
        payload["featured_media"] = media_id
    if author_id is not None:
        payload["author"] = author_id

    category_id = meta.get("category_id")
    if category_id:
        payload["categories"] = [category_id]
    tag_ids = meta.get("tag_ids") or []
    if tag_ids:
        payload["tags"] = tag_ids

    headers = {"Content-Type": "application/json"}
    headers.update(_basic_auth_header(username, application_password))
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code not in {200, 201}:
        raise WordPressError(f"Failed to update post: {response.status_code} {response.text}")

    return response.json()

def get_user_id_by_username(
    base_url: str,
    username: str,
    application_password: str,
    target_username: str,
) -> int | None:
    headers = _basic_auth_header(username, application_password)
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/users"
    params = {"search": target_username, "per_page": 100}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise WordPressError(f"Failed to fetch users: {response.status_code} {response.text}")
    data = response.json()
    for user in data:
        if user.get("slug") == target_username or user.get("name") == target_username:
            return user.get("id")
    return None

def get_wp_categories(base_url: str, username: str, application_password: str) -> list[dict]:
    global _CACHED_CATEGORIES
    if _CACHED_CATEGORIES is not None:
        return _CACHED_CATEGORIES
    headers = _basic_auth_header(username, application_password)
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/categories"
    params = {"per_page": 100}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise WordPressError(f"Failed to fetch categories: {response.status_code} {response.text}")
    data = response.json()
    categories = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "slug": item.get("slug"),
            "description": item.get("description"),
        }
        for item in data
    ]
    _CACHED_CATEGORIES = categories
    return categories


def get_wp_tags(base_url: str, username: str, application_password: str) -> list[dict]:
    global _CACHED_TAGS
    if _CACHED_TAGS is not None:
        return _CACHED_TAGS
    headers = _basic_auth_header(username, application_password)
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/tags"
    params = {"per_page": 100}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise WordPressError(f"Failed to fetch tags: {response.status_code} {response.text}")
    data = response.json()
    tags = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "slug": item.get("slug"),
            "description": item.get("description"),
        }
        for item in data
    ]
    _CACHED_TAGS = tags
    return tags


def create_wp_tag(base_url: str, username: str, application_password: str, tag_name: str, max_retries: int = 3) -> dict:
    import time
    url = f"{base_url}/wp-json/wp/v2/tags"
    auth = (username, application_password)
    payload = {"name": tag_name}
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, auth=auth, timeout=30)
            if response.status_code == 201:
                return response.json()  # Return full tag dict
            elif response.status_code == 400:
                error_data = response.json()
                if error_data.get("code") == "term_exists":
                    # Fetch the existing tag to return full data
                    term_id = error_data["data"]["term_id"]
                    existing_tag = requests.get(f"{url}/{term_id}", auth=auth, timeout=30)
                    if existing_tag.status_code == 200:
                        return existing_tag.json()
                    # Fallback: return minimal dict with just ID
                    return {"id": term_id, "name": tag_name, "slug": tag_name.lower().replace(" ", "-")}
            raise WordPressError(f"Failed to create tag '{tag_name}': {response.status_code} {response.text}")
        except requests.exceptions.ReadTimeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"Timeout creating tag '{tag_name}', retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            else:
                raise WordPressError(f"Failed to create tag '{tag_name}' after {max_retries} attempts: timeout")
