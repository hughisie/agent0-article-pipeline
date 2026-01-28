#!/usr/bin/env python3
"""
Quick test to verify Ghost publishing works for RetroShell profile.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from publishing import create_publisher, PublishingError
from agent0_gui.profile_manager import get_all_profiles
from main import detect_profile_from_path
from ghost_metadata import optimize_article_metadata_for_ghost

def test_profile_detection():
    """Test that RetroShell profile is detected from file path"""
    test_path = "/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/09. Feed Finder/retro_gaming/2026-01/13/7am Scrape/01. Priority - Retro Gaming/115-test.json"

    print("Testing profile detection...")
    profile = detect_profile_from_path(test_path)

    if profile:
        print(f"✓ Detected profile: {profile['name']}")
        print(f"  Platform: {profile.get('publishing_platform')}")
        return profile
    else:
        print("✗ No profile detected")
        return None


def test_publisher_creation(profile):
    """Test creating Ghost publisher from profile"""
    print("\nTesting publisher creation...")

    try:
        platform_config = json.loads(profile.get("platform_config") or "{}")

        if not platform_config:
            print("✗ No platform config found")
            return None

        publisher = create_publisher(platform_config)
        print(f"✓ Publisher created: {publisher.platform_name}")
        print(f"  API URL: {platform_config.get('api_url')}")

        # Test connection
        is_connected = publisher.validate_connection()
        if is_connected:
            print("✓ Connection test passed")
        else:
            print("✗ Connection test failed")
            return None

        return publisher

    except Exception as e:
        print(f"✗ Publisher creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_metadata_optimization():
    """Test Ghost metadata optimization"""
    print("\nTesting metadata optimization...")

    test_meta = {
        "meta_title": "This is a very long title that exceeds the 60 character limit for Ghost CMS and needs to be truncated properly",
        "meta_description": "This is a very long description that exceeds the 145 character limit for Ghost CMS and needs to be truncated properly to fit within the social media preview constraints that Ghost enforces",
        "primary_keyword": "retro gaming",
        "slug": "test-article",
        "tags": ["gaming", "retro", "n64", "jrpg", "recompilation", "pc", "mod", "extra1", "extra2"],
        "excerpt": "Test excerpt"
    }

    print(f"Original title length: {len(test_meta['meta_title'])}")
    print(f"Original description length: {len(test_meta['meta_description'])}")
    print(f"Original tags count: {len(test_meta['tags'])}")

    optimized = optimize_article_metadata_for_ghost(test_meta)

    print(f"\nOptimized title length: {len(optimized['meta_title'])}")
    print(f"  Title: {optimized['meta_title']}")
    print(f"Optimized description length: {len(optimized['meta_description'])}")
    print(f"  Description: {optimized['meta_description']}")
    print(f"Optimized tags count: {len(optimized['tags'])}")

    if len(optimized['meta_title']) <= 60:
        print("✓ Title within limit")
    else:
        print("✗ Title exceeds limit")

    if len(optimized['meta_description']) <= 145:
        print("✓ Description within limit")
    else:
        print("✗ Description exceeds limit")

    if len(optimized['tags']) <= 7:
        print("✓ Tags within limit")
    else:
        print("✗ Tags exceed limit")


def test_create_draft():
    """Test creating a draft post on Ghost"""
    print("\nTesting draft post creation...")

    profile = test_profile_detection()
    if not profile:
        print("✗ Cannot test without profile")
        return False

    publisher = test_publisher_creation(profile)
    if not publisher:
        print("✗ Cannot test without publisher")
        return False

    # Create a simple test post
    test_meta = {
        "meta_title": "Test Article from RetroShell Profile",
        "meta_description": "This is a test article to verify Ghost publishing works correctly with the multi-profile system.",
        "primary_keyword": "retro gaming",
        "slug": "test-retroshell-" + str(int(__import__('time').time())),
        "tags": ["test", "retroshell", "automation"],
        "excerpt": "Test article for Ghost CMS",
        "wp_block_content": """
<!-- wp:heading {"level":1} -->
<h1>Test Article for RetroShell</h1>
<!-- /wp:heading -->

<!-- wp:paragraph -->
<p>This is a test article created by the automated article processing system.</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>The system successfully:</p>
<!-- /wp:paragraph -->

<!-- wp:list -->
<ul>
<li>Detected the RetroShell profile from the file path</li>
<li>Created a Ghost publisher with the correct credentials</li>
<li>Optimized metadata for Ghost's requirements (60 char title, 145 char description)</li>
<li>Created this draft post with featured image and tags</li>
</ul>
<!-- /wp:list -->

<!-- wp:paragraph -->
<p>This demonstrates that the multi-profile publishing system is working correctly!</p>
<!-- /wp:paragraph -->
"""
    }

    # Optimize for Ghost
    test_meta = optimize_article_metadata_for_ghost(test_meta)

    try:
        print("Creating draft post...")
        post_result = publisher.create_draft_post(
            meta=test_meta,
            featured_media_id=None,  # No image for test
            author_id=None
        )

        print(f"\n✓ Draft created successfully!")
        print(f"  Post ID: {post_result.post_id}")
        print(f"  URL: {post_result.url}")
        print(f"  Status: {post_result.status}")

        return True

    except Exception as e:
        print(f"\n✗ Draft creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Ghost Publishing Test")
    print("=" * 60)

    test_metadata_optimization()
    result = test_create_draft()

    print("\n" + "=" * 60)
    if result:
        print("✓ All tests passed!")
        print("Ghost publishing is working correctly.")
    else:
        print("✗ Some tests failed")
    print("=" * 60)

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
