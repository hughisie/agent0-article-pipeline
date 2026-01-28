"""
WordPress publishing platform implementation.

This module wraps the existing wordpress_client.py functions into the PublishingClient interface.
"""

from typing import Any, Dict, List, Optional

from publishing.base_publisher import (
    PublishingClient,
    PublishingError,
    MediaUploadResult,
    PostResult,
    TaxonomyItem,
)
import wordpress_client


class WordPressPublisher(PublishingClient):
    """WordPress implementation of the PublishingClient interface"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config["base_url"]
        self.username = config["username"]
        self.password = config["application_password"]
        self.platform_name = "WordPress"

    def upload_media(
        self,
        image_url: str,
        alt_text: Optional[str] = None,
        title: Optional[str] = None
    ) -> MediaUploadResult:
        """Upload media from URL to WordPress"""
        try:
            result = wordpress_client.upload_media_from_url(
                self.base_url,
                self.username,
                self.password,
                image_url,
                alt_text
            )
            # Handle case where upload was skipped (e.g., base64 data URI)
            if result is None or result == (None, None):
                print(f"Skipped image upload for: {image_url[:80]}...")
                return MediaUploadResult(
                    media_id=None,
                    url=None,
                    platform_specific={"source_url": None}
                )
            media_id, source_url = result
            return MediaUploadResult(
                media_id=media_id,
                url=source_url,
                platform_specific={"source_url": source_url}
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress media upload failed: {e}")

    def create_draft_post(
        self,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """Create a draft post on WordPress"""
        try:
            response = wordpress_client.create_draft_post(
                self.base_url,
                self.username,
                self.password,
                meta,
                featured_media_id,
                author_id
            )
            return PostResult(
                post_id=response.get("id"),
                url=response.get("link"),
                status=response.get("status", "draft"),
                platform_specific=response
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress post creation failed: {e}")

    def update_post(
        self,
        post_id: Any,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """Update an existing post on WordPress"""
        try:
            response = wordpress_client.update_post(
                self.base_url,
                self.username,
                self.password,
                int(post_id),
                meta,
                featured_media_id,
                author_id
            )
            return PostResult(
                post_id=response.get("id"),
                url=response.get("link"),
                status=response.get("status", "draft"),
                platform_specific=response
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress post update failed: {e}")

    def get_taxonomies(self) -> Dict[str, List[TaxonomyItem]]:
        """Get all WordPress categories and tags"""
        try:
            categories = wordpress_client.get_wp_categories(
                self.base_url,
                self.username,
                self.password
            )
            tags = wordpress_client.get_wp_tags(
                self.base_url,
                self.username,
                self.password
            )

            return {
                "categories": [
                    TaxonomyItem(
                        id=cat["id"],
                        name=cat["name"],
                        slug=cat["slug"],
                        type="category",
                        platform_specific=cat
                    )
                    for cat in categories
                ],
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
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress taxonomy fetch failed: {e}")

    def create_taxonomy_item(
        self,
        name: str,
        taxonomy_type: str,
        slug: Optional[str] = None,
        parent_id: Optional[Any] = None
    ) -> TaxonomyItem:
        """Create a new WordPress tag (categories not supported in this implementation)"""
        if taxonomy_type != "tag":
            raise PublishingError(f"Creating {taxonomy_type} not supported, only tags can be created")

        try:
            response = wordpress_client.create_wp_tag(
                self.base_url,
                self.username,
                self.password,
                name
            )
            return TaxonomyItem(
                id=response.get("id"),
                name=response.get("name"),
                slug=response.get("slug"),
                type="tag",
                platform_specific=response
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress tag creation failed: {e}")

    def get_recent_posts(
        self,
        months_back: int = 3,
        max_posts: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent posts from WordPress"""
        try:
            return wordpress_client.get_recent_posts(
                self.base_url,
                self.username,
                self.password,
                months_back,
                max_posts
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress fetch recent posts failed: {e}")

    def validate_connection(self) -> bool:
        """Test if the WordPress connection works"""
        try:
            # Try to fetch categories as a simple connection test
            wordpress_client.get_wp_categories(
                self.base_url,
                self.username,
                self.password
            )
            return True
        except Exception:
            return False

    def get_user_id_by_username(self, target_username: str) -> Optional[int]:
        """Get WordPress user ID by username (WordPress-specific helper)"""
        try:
            return wordpress_client.get_user_id_by_username(
                self.base_url,
                self.username,
                self.password,
                target_username
            )
        except wordpress_client.WordPressError as e:
            raise PublishingError(f"WordPress user lookup failed: {e}")
