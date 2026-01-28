"""
Base abstract class for publishing platform integrations.

This module defines the common interface that all publishing platforms (WordPress, Ghost, etc.)
must implement to work with the article processing pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MediaUploadResult:
    """Result from uploading media to a publishing platform"""
    media_id: Any
    url: str
    platform_specific: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PostResult:
    """Result from creating or updating a post"""
    post_id: Any
    url: str
    status: str
    platform_specific: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaxonomyItem:
    """Represents a category, tag, or other taxonomy item"""
    id: Any
    name: str
    slug: str
    type: str  # "category", "tag", etc.
    platform_specific: Dict[str, Any] = field(default_factory=dict)


class PublishingClient(ABC):
    """
    Abstract base class for publishing platform clients.

    All platform implementations (WordPress, Ghost, etc.) must inherit from this class
    and implement all abstract methods.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the publishing client with platform-specific configuration.

        Args:
            config: Dictionary containing platform configuration
                   (credentials, URLs, etc.)
        """
        self.config = config
        self.platform_name = config.get("platform", "unknown")

    @abstractmethod
    def upload_media(
        self,
        image_url: str,
        alt_text: Optional[str] = None,
        title: Optional[str] = None
    ) -> MediaUploadResult:
        """
        Upload media from a URL to the publishing platform.

        Args:
            image_url: URL of the image to upload
            alt_text: Optional alt text for the image
            title: Optional title for the media

        Returns:
            MediaUploadResult with the uploaded media ID and URL

        Raises:
            PublishingError: If the upload fails
        """
        pass

    @abstractmethod
    def create_draft_post(
        self,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """
        Create a draft post on the publishing platform.

        Args:
            meta: Dictionary containing post metadata (title, content, excerpt, etc.)
            featured_media_id: Optional ID of the featured image
            author_id: Optional author ID

        Returns:
            PostResult with the created post ID and URL

        Raises:
            PublishingError: If the post creation fails
        """
        pass

    @abstractmethod
    def update_post(
        self,
        post_id: Any,
        meta: Dict[str, Any],
        featured_media_id: Optional[Any] = None,
        author_id: Optional[Any] = None
    ) -> PostResult:
        """
        Update an existing post on the publishing platform.

        Args:
            post_id: ID of the post to update
            meta: Dictionary containing updated post metadata
            featured_media_id: Optional ID of the featured image
            author_id: Optional author ID

        Returns:
            PostResult with the updated post ID and URL

        Raises:
            PublishingError: If the update fails
        """
        pass

    @abstractmethod
    def get_taxonomies(self) -> Dict[str, List[TaxonomyItem]]:
        """
        Get all available taxonomies (categories, tags, etc.) from the platform.

        Returns:
            Dictionary mapping taxonomy type to list of taxonomy items
            Example: {"categories": [...], "tags": [...]}

        Raises:
            PublishingError: If fetching taxonomies fails
        """
        pass

    @abstractmethod
    def create_taxonomy_item(
        self,
        name: str,
        taxonomy_type: str,
        slug: Optional[str] = None,
        parent_id: Optional[Any] = None
    ) -> TaxonomyItem:
        """
        Create a new taxonomy item (category, tag, etc.).

        Args:
            name: Name of the taxonomy item
            taxonomy_type: Type of taxonomy ("category", "tag", etc.)
            slug: Optional slug (will be auto-generated if not provided)
            parent_id: Optional parent taxonomy item ID (for hierarchical taxonomies)

        Returns:
            TaxonomyItem with the created item details

        Raises:
            PublishingError: If creation fails
        """
        pass

    @abstractmethod
    def get_recent_posts(
        self,
        months_back: int = 3,
        max_posts: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent posts from the publishing platform.

        Args:
            months_back: Number of months to look back
            max_posts: Maximum number of posts to retrieve

        Returns:
            List of dictionaries containing post data

        Raises:
            PublishingError: If fetching posts fails
        """
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Test if the connection to the publishing platform works.

        Returns:
            True if connection is valid, False otherwise
        """
        pass


class PublishingError(Exception):
    """Base exception for publishing-related errors"""
    pass
