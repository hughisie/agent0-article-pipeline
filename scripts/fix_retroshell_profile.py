#!/usr/bin/env python3
"""
Fix RetroShell profile configuration for Ghost CMS.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent0_gui.db import get_conn
from agent0_gui.profile_manager import get_all_profiles

def fix_retroshell_profile():
    """Update RetroShell profile with correct Ghost configuration"""

    # Ghost configuration
    ghost_config = {
        "platform": "ghost",
        "api_url": "https://visionary-tiger.pikapod.net",
        "admin_api_key": "69665065c941b50001ad0bff:9a1c61cbe2b602b98adb5dd13eec7c40c1dde90059b0fb32026c1e2d4c355e6d",
        "content_api_key": "e09c2507c90448c85ae1c4bb24",
        "gdrive_subfolder": "RetroShell",
        "sitemap_url": "https://www.retroshell.com/sitemap.xml"
    }

    # Correct input directory for RetroShell articles
    input_dir = "/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/09. Feed Finder/retro_gaming"
    output_dir = "output/retroshell"

    profiles = get_all_profiles()
    retroshell_profile = None

    for profile in profiles:
        if profile["name"] == "RetroShell":
            retroshell_profile = profile
            break

    if not retroshell_profile:
        print("✗ RetroShell profile not found!")
        return False

    print(f"Found RetroShell profile (ID: {retroshell_profile['id']})")
    print(f"\nCurrent configuration:")
    print(f"  Platform: {retroshell_profile.get('publishing_platform')}")
    print(f"  Input Dir: {retroshell_profile['input_dir']}")
    print(f"  Output Dir: {retroshell_profile['output_dir']}")

    # Update profile
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET publishing_platform = ?,
                platform_config = ?,
                input_dir = ?,
                output_dir = ?
            WHERE id = ?
            """,
            (
                "ghost",
                json.dumps(ghost_config, indent=2),
                input_dir,
                output_dir,
                retroshell_profile["id"]
            )
        )
        conn.commit()

    print(f"\n✓ Updated RetroShell profile:")
    print(f"  Platform: ghost")
    print(f"  Input Dir: {input_dir}")
    print(f"  Output Dir: {output_dir}")
    print(f"  API URL: {ghost_config['api_url']}")
    print(f"  Google Drive Subfolder: {ghost_config['gdrive_subfolder']}")

    # Test connection
    print("\nTesting Ghost connection...")
    from publishing import create_publisher

    try:
        publisher = create_publisher(ghost_config)
        is_connected = publisher.validate_connection()

        if is_connected:
            print("✓ Ghost connection successful!")
            return True
        else:
            print("✗ Ghost connection failed")
            return False
    except Exception as e:
        print(f"✗ Failed to test connection: {e}")
        return False

if __name__ == "__main__":
    success = fix_retroshell_profile()
    sys.exit(0 if success else 1)
