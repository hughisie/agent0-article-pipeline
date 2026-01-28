"""
Ghost CMS publishing platform implementation.

This module implements the Ghost Admin API v5.0 with JWT authentication.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import jwt
import requests

from publishing.base_publisher import (
    PublishingClient,
    PublishingError,
    MediaUploadResult,
    PostResult,
    TaxonomyItem,
)


class GhostPublisher(PublishingClient):
    """Ghost CMS implementation of the PublishingClient interface"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config["api_url"].rstrip("/")
        self.admin_api_key = config["admin_api_key"]
        self.content_api_key = config.get("content_api_key")
        self.platform_name = "Ghost"

        # Parse admin API key (format: id:secret)
        if ":" not in self.admin_api_key:
            raise PublishingError("Ghost admin_api_key must be in format 'id:secret'")

        self.key_id, self.key_secret = self.admin_api_key.split(":", 1)

        # Cache for tags
        self._tags_cache: Optional[List[Dict]] = None

    def _generate_jwt(self) -> str:
        """Generate a 5-minute JWT token for Ghost Admin API"""
        iat = int(time.time())
        exp = iat + (5 * 60)  # 5 minutes

        header = {"alg": "HS256", "typ": "JWT", "kid": self.key_id}
        payload = {"iat": iat, "exp": exp, "aud": "/admin/"}

        try:
            secret_bytes = bytes.fromhex(self.key_secret)
        except ValueError:
            raise PublishingError("Ghost API key secret must be valid hex string")

        return jwt.encode(payload, secret_bytes, algorithm="HS256", headers=header)

    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Get headers with JWT authentication for Ghost Admin API"""
        token = self._generate_jwt()
        return {
            "Authorization": f"Ghost {token}",
            "Accept-Version": "v5.0",
            "Content-Type": content_type,
        }

    def _convert_blocks_to_html(self, wp_blocks: str) -> str:
        """
        Convert WordPress block content to clean HTML for Ghost.
        Strips WordPress block comments and cleans up markup.
        """
        if not wp_blocks:
            return ""

        # Remove WordPress block comments
        html = re.sub(r'<!-- wp:[^>]+ -->', '', wp_blocks)
        html = re.sub(r'<!-- /wp:[^>]+ -->', '', html)

        # Clean up extra whitespace
        html = re.sub(r'\n\s*\n', '\n\n', html)

        return html.strip()

    def _map_taxonomies_to_tags(self, meta: Dict[str, Any]) -> List[str]:
        """
        Convert WordPress categories and tags to Ghost tags.
        Categories become internal tags (prefixed with #).
        """
        tag_names = []

        # Add category as internal tag (prefixed with #)
        if meta.get("category_name"):
            tag_names.append(f"#{meta['category_name']}")

        # Add regular tags
        for tag_dict in meta.get("tags", []):
            if isinstance(tag_dict, dict):
                tag_name = tag_dict.get("name")
            else:
                tag_name = str(tag_dict)

            if tag_name and tag_name not in tag_names:
                tag_names.append(tag_name)

        return tag_names

    def _get_or_create_tags(self, tag_names: List[str]) -> List[Dict]:
        """Get or create Ghost tags by name"""
        if not tag_names:
            return []

        # Get existing tags
        existing_tags = self._get_all_tags()
        existing_map = {tag["name"].lower(): tag for tag in existing_tags}

        result_tags = []
        for tag_name in tag_names:
            tag_name_lower = tag_name.lower()

            if tag_name_lower in existing_map:
                result_tags.append(existing_map[tag_name_lower])
            else:
                # Create new tag
                try:
                    new_tag = self._create_tag(tag_name)
                    result_tags.append(new_tag)
                    # Update cache
                    existing_map[tag_name_lower] = new_tag
                except Exception as e:
                    print(f"Warning: Failed to create tag '{tag_name}': {e}")

        return result_tags

    def _get_all_tags(self) -> List[Dict]:
        """Get all Ghost tags (with caching)"""
        if self._tags_cache is not None:
            return self._tags_cache

        url = urljoin(self.api_url, "/ghost/api/admin/tags/")
        headers = self._get_headers()

        try:
            response = requests.get(
                url,
                headers=headers,
                params={"limit": "all"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                self._tags_cache = data.get("tags", [])
                return self._tags_cache
            else:
                print(f"Warning: Failed to fetch Ghost tags: {response.status_code}")
                return []

        except Exception as e:
            print(f"Warning: Error fetching Ghost tags: {e}")
            return []

    def _create_tag(self, name: str, slug: Optional[str] = None) -> Dict:
        """Create a new Ghost tag"""
        url = urljoin(self.api_url, "/ghost/api/admin/tags/")
        headers = self._get_headers()

        payload = {
            "tags": [
                {
                    "name": name,
                    "slug": slug,
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code not in {200, 201}:
            raise PublishingError(
                f"Ghost tag creation failed: {response.status_code} {response.text}"
            )

        data = response.json()
        return data.get("tags", [{}])[0]

    def upload_media(
        self,
        image_url: str,
        alt_text: Optional[str] = None,
        title: Optional[str] = None
    ) -> MediaUploadResult:
        """Upload media from URL to Ghost"""
        try:
            # Download image
            download = requests.get(image_url, stream=True, timeout=60)
            if download.status_code != 200:
                raise PublishingError(f"Failed to download image: {download.status_code}")

            # Extract filename
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            filename = parsed.path.rsplit("/", 1)[-1] or "image.jpg"

            # Upload to Ghost
            url = urljoin(self.api_url, "/ghost/api/admin/images/upload/")
            headers = {
                "Authorization": f"Ghost {self._generate_jwt()}",
                "Accept-Version": "v5.0",
            }

            files = {
                "file": (filename, download.content, download.headers.get("Content-Type", "image/jpeg"))
            }

            response = requests.post(url, headers=headers, files=files, timeout=60)

            if response.status_code not in {200, 201}:
                raise PublishingError(
                    f"Ghost image upload failed: {response.status_code} {response.text}"
                )

            data = response.json()
            image_url = data.get("images", [{}])[0].get("url")

            if not image_url:
                raise PublishingError("Ghost image upload did not return URL")

            return MediaUploadResult(
                media_id=image_url,  # Ghost doesn't have media IDs, use URL
                url=image_url,
                platform_specific=data
            )

        except requests.RequestException as e:
            raise PublishingError(f"Ghost media upload failed: {e}")

    def create_draft_post(
        self,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """Create a draft post on Ghost"""
        try:
            # Convert WordPress blocks to HTML
            content = self._convert_blocks_to_html(
                meta.get("wp_block_content") or meta.get("wp_html_content") or ""
            )

            # Map taxonomies to Ghost tags
            tag_names = self._map_taxonomies_to_tags(meta)
            tags = self._get_or_create_tags(tag_names)

            # Build post payload
            post_data = {
                "title": meta.get("meta_title", ""),
                "html": content,
                "status": "draft",
                "slug": meta.get("slug"),
                "custom_excerpt": meta.get("excerpt"),
                "feature_image": featured_media_id,  # URL, not ID
                "featured": True,  # Mark post as featured
                "tags": [{"id": tag["id"]} for tag in tags if tag.get("id")],
                "meta_title": meta.get("meta_title", ""),  # SEO meta title
                "meta_description": meta.get("meta_description", ""),  # SEO meta description
            }

            # Add author if provided (Ghost author IDs are strings)
            # Note: Ghost uses its own author system, WordPress author IDs won't work
            # If no author provided, Ghost uses the default author for the API key
            if author_id and isinstance(author_id, str):
                post_data["authors"] = [{"id": str(author_id)}]

            payload = {"posts": [post_data]}

            url = urljoin(self.api_url, "/ghost/api/admin/posts/")
            headers = self._get_headers()

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                params={"source": "html"},
                timeout=30
            )

            if response.status_code not in {200, 201}:
                raise PublishingError(
                    f"Ghost post creation failed: {response.status_code} {response.text}"
                )

            data = response.json()
            post = data.get("posts", [{}])[0]

            return PostResult(
                post_id=post.get("id"),
                url=post.get("url"),
                status=post.get("status", "draft"),
                platform_specific=post
            )

        except requests.RequestException as e:
            raise PublishingError(f"Ghost post creation failed: {e}")

    def update_post(
        self,
        post_id: Any,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """Update an existing post on Ghost"""
        try:
            # Convert WordPress blocks to HTML
            content = self._convert_blocks_to_html(
                meta.get("wp_block_content") or meta.get("wp_html_content") or ""
            )

            # Map taxonomies to Ghost tags
            tag_names = self._map_taxonomies_to_tags(meta)
            tags = self._get_or_create_tags(tag_names)

            # Build post payload
            post_data = {
                "title": meta.get("meta_title", ""),
                "html": content,
                "slug": meta.get("slug"),
                "custom_excerpt": meta.get("excerpt"),
                "feature_image": featured_media_id,
                "featured": True,  # Mark post as featured
                "tags": [{"id": tag["id"]} for tag in tags if tag.get("id")],
                "meta_title": meta.get("meta_title", ""),  # SEO meta title
                "meta_description": meta.get("meta_description", ""),  # SEO meta description
                "updated_at": meta.get("updated_at"),  # Required for updates
            }

            # Add author if provided (Ghost author IDs are strings)
            # Note: Ghost uses its own author system, WordPress author IDs won't work
            if author_id and isinstance(author_id, str):
                post_data["authors"] = [{"id": str(author_id)}]

            payload = {"posts": [post_data]}

            url = urljoin(self.api_url, f"/ghost/api/admin/posts/{post_id}/")
            headers = self._get_headers()

            response = requests.put(
                url,
                headers=headers,
                json=payload,
                params={"source": "html"},
                timeout=30
            )

            if response.status_code not in {200, 201}:
                raise PublishingError(
                    f"Ghost post update failed: {response.status_code} {response.text}"
                )

            data = response.json()
            post = data.get("posts", [{}])[0]

            return PostResult(
                post_id=post.get("id"),
                url=post.get("url"),
                status=post.get("status", "draft"),
                platform_specific=post
            )

        except requests.RequestException as e:
            raise PublishingError(f"Ghost post update failed: {e}")

    def get_taxonomies(self) -> Dict[str, List[TaxonomyItem]]:
        """Get all Ghost tags (Ghost doesn't have categories)"""
        tags = self._get_all_tags()

        return {
            "tags": [
                TaxonomyItem(
                    id=tag["id"],
                    name=tag["name"],
                    slug=tag["slug"],
                    type="tag",
                    platform_specific=tag
                )
                for tag in tags
            ]
        }

    def create_taxonomy_item(
        self,
        name: str,
        taxonomy_type: str,
        slug: Optional[str] = None,
        parent_id: Optional[Any] = None
    ) -> TaxonomyItem:
        """Create a new Ghost tag"""
        if taxonomy_type != "tag":
            raise PublishingError(f"Ghost only supports tags, not {taxonomy_type}")

        try:
            tag = self._create_tag(name, slug)
            # Clear cache
            self._tags_cache = None

            return TaxonomyItem(
                id=tag["id"],
                name=tag["name"],
                slug=tag["slug"],
                type="tag",
                platform_specific=tag
            )
        except Exception as e:
            raise PublishingError(f"Ghost tag creation failed: {e}")

    def get_recent_posts(
        self,
        months_back: int = 3,
        max_posts: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent posts from Ghost"""
        try:
            url = urljoin(self.api_url, "/ghost/api/admin/posts/")
            headers = self._get_headers()

            params = {
                "limit": min(max_posts, 100),
                "order": "published_at DESC",
                "filter": "status:published",
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code != 200:
                raise PublishingError(
                    f"Ghost fetch posts failed: {response.status_code} {response.text}"
                )

            data = response.json()
            posts = data.get("posts", [])

            # Convert to common format
            result = []
            for post in posts:
                result.append({
                    "id": post.get("id"),
                    "title": post.get("title"),
                    "url": post.get("url"),
                    "date": post.get("published_at"),
                    "excerpt": post.get("custom_excerpt", ""),
                    "content_snippet": post.get("plaintext", "")[:500],
                    "tags": [tag.get("name") for tag in post.get("tags", [])],
                })

            return result[:max_posts]

        except requests.RequestException as e:
            raise PublishingError(f"Ghost fetch posts failed: {e}")

    def validate_connection(self) -> bool:
        """Test if the Ghost connection works"""
        try:
            url = urljoin(self.api_url, "/ghost/api/admin/site/")
            headers = self._get_headers()

            response = requests.get(url, headers=headers, timeout=10)
            return response.status_code == 200

        except Exception:
            return False
