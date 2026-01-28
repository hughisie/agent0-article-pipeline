"""
Publishing platform abstraction layer.

This package provides a unified interface for publishing to different platforms
(WordPress, Ghost, etc.) through the PublishingClient abstract base class.
"""

from typing import Dict, Any

from publishing.base_publisher import (
    PublishingClient,
    PublishingError,
    MediaUploadResult,
    PostResult,
    TaxonomyItem,
)
from publishing.wordpress_publisher import WordPressPublisher
from publishing.ghost_publisher import GhostPublisher


def create_publisher(platform_config: Dict[str, Any]) -> PublishingClient:
    """
    Factory function to create the appropriate publisher based on platform configuration.

    Args:
        platform_config: Dictionary containing platform configuration.
                        Must include a "platform" key with value "wordpress" or "ghost".

    Returns:
        PublishingClient instance for the specified platform

    Raises:
        ValueError: If platform is not supported or configuration is invalid
        PublishingError: If publisher initialization fails

    Example:
        >>> config = {
        ...     "platform": "wordpress",
        ...     "base_url": "https://example.com",
        ...     "username": "admin",
        ...     "application_password": "xxxx"
        ... }
        >>> publisher = create_publisher(config)
        >>> publisher.validate_connection()
        True
    """
    if not platform_config:
        raise ValueError("Platform configuration is required")

    platform = platform_config.get("platform", "").lower()

    if not platform:
        raise ValueError("Platform must be specified in configuration")

    if platform == "wordpress":
        return WordPressPublisher(platform_config)
    elif platform == "ghost":
        return GhostPublisher(platform_config)
    else:
        raise ValueError(
            f"Unsupported platform: {platform}. "
            f"Supported platforms: wordpress, ghost"
        )


__all__ = [
    "create_publisher",
    "PublishingClient",
    "PublishingError",
    "MediaUploadResult",
    "PostResult",
    "TaxonomyItem",
    "WordPressPublisher",
    "GhostPublisher",
]
