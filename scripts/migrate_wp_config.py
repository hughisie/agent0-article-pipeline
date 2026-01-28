#!/usr/bin/env python3
"""
Migrate WordPress configuration from config.json to the Default profile's platform_config.
This is a one-time migration script to enable the multi-platform profile system.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent0_gui.db import get_conn
from agent0_gui.profile_manager import get_all_profiles, create_profile
from config import load_config


def migrate_wordpress_config():
    """Move WordPress config from config.json to profiles database"""
    print("=" * 60)
    print("WordPress Configuration Migration")
    print("=" * 60)

    # Load existing config
    try:
        config = load_config()
    except Exception as e:
        print(f"✗ Failed to load config.json: {e}")
        return False

    # Extract WordPress settings
    wp_config = {
        "platform": "wordpress",
        "base_url": config.get("WP_BASE_URL"),
        "username": config.get("WP_USERNAME"),
        "application_password": config.get("WP_APPLICATION_PASSWORD"),
        "sitemap_url": config.get("WP_SITEMAP_URL", "https://barna.news/sitemap.xml")
    }

    # Validate we have the required fields
    if not wp_config["base_url"] or not wp_config["username"] or not wp_config["application_password"]:
        print("✗ Missing required WordPress configuration in config.json")
        print("  Required: WP_BASE_URL, WP_USERNAME, WP_APPLICATION_PASSWORD")
        return False

    print(f"\n✓ Found WordPress configuration:")
    print(f"  Base URL: {wp_config['base_url']}")
    print(f"  Username: {wp_config['username']}")
    print(f"  Sitemap: {wp_config['sitemap_url']}")

    # Find Default profile (or create one)
    profiles = get_all_profiles()
    if profiles:
        profile = profiles[0]
        print(f"\n✓ Found existing profile: '{profile['name']}' (ID: {profile['id']})")
    else:
        print("\n! No profiles found, creating Default profile...")
        profile = create_profile(
            name="Default",
            input_dir="current",
            output_dir="output",
            description="Default WordPress profile for Barcelona news"
        )
        print(f"✓ Created profile: '{profile['name']}' (ID: {profile['id']})")

    # Update profile with platform config
    try:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE profiles
                SET publishing_platform = ?, platform_config = ?
                WHERE id = ?
                """,
                ("wordpress", json.dumps(wp_config, indent=2), profile["id"])
            )
            conn.commit()
        print(f"\n✓ Successfully migrated WordPress config to profile '{profile['name']}' (ID: {profile['id']})")
    except Exception as e:
        print(f"\n✗ Failed to update profile: {e}")
        return False

    # Verify the migration
    with get_conn() as conn:
        row = conn.execute(
            "SELECT publishing_platform, platform_config FROM profiles WHERE id = ?",
            (profile["id"],)
        ).fetchone()

        if row:
            stored_platform = row["publishing_platform"]
            stored_config = json.loads(row["platform_config"] or "{}")

            print(f"\n✓ Verification:")
            print(f"  Platform: {stored_platform}")
            print(f"  Config stored: {len(stored_config)} keys")
            print(f"  Base URL: {stored_config.get('base_url')}")

    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. The Default profile now has WordPress configuration")
    print("  2. You can keep WP_* keys in config.json as a backup")
    print("  3. Or remove them since they're now in the database")
    print("  4. Create additional profiles (e.g., RetroShell for Ghost) via the dashboard")
    print("  5. Test the system by processing an article")

    return True


if __name__ == "__main__":
    try:
        success = migrate_wordpress_config()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
