import json
import os
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from PIL import Image
from io import BytesIO


GDRIVE_BASE_PATH = "/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/10. Post Content"


def extract_article_number(filename: str) -> str:
    """Extract article number from filename like '01-Title...' returns '01'"""
    match = re.match(r'^(\d+)-', filename)
    return match.group(1) if match else "00"


def slugify_headline(headline: str, max_length: int = 80) -> str:
    """Convert headline to safe directory name."""
    # Remove special characters but keep alphanumeric, spaces, and common punctuation
    slug = re.sub(r'[<>:"/\\|?*]', '', headline)
    # Replace multiple spaces with single space
    slug = re.sub(r'\s+', ' ', slug).strip()
    # Truncate to max length at word boundary
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit(' ', 1)[0]
    return slug


def save_images_to_gdrive(
    image_urls: List[str],
    article_date: str,
    json_filename: str,
    profile_id: Optional[int] = None,
    translated_headline: Optional[str] = None,
    article_number: Optional[str] = None,
) -> List[str]:
    """
    Download and save images to Google Drive with profile-specific structure:
    BASE/ProfileFolder/YYYY/MM.MMM/DD/NUMBER - TRANSLATED_HEADLINE/Image1.jpg

    Args:
        image_urls: List of image URLs to download
        article_date: ISO format date string (ignored - uses current processing date)
        json_filename: Original JSON filename (fallback if no translated_headline)
        profile_id: Optional profile ID to determine subfolder (uses active profile if not provided)
        translated_headline: The English translated headline to use for folder name
        article_number: The article number (e.g., "11") to prefix the folder

    Returns:
        List of saved file paths
    """
    saved_paths = []

    # Get profile information
    from agent0_gui.profile_manager import get_profile_by_id, get_active_profile

    profile = get_profile_by_id(profile_id) if profile_id else get_active_profile()
    if not profile:
        print("Warning: No profile found, using default path")
        gdrive_subfolder = "Default"
    else:
        # Get profile's gdrive_subfolder from platform_config
        platform_config = json.loads(profile.get("platform_config") or "{}")
        gdrive_subfolder = platform_config.get("gdrive_subfolder", profile["name"])

    print(f"Using Google Drive subfolder: {gdrive_subfolder}")

    # Use current processing date, not article date
    dt = datetime.now()

    # Build folder name from article number and translated headline
    if article_number is None:
        article_number = extract_article_number(json_filename)

    if translated_headline:
        # Use translated headline for folder name
        headline_slug = slugify_headline(translated_headline)
        folder_name = f"{article_number} - {headline_slug}"
    else:
        # Fallback to original filename
        folder_name = json_filename.replace('.json', '').replace('/', '_').replace('\\', '_')

    # Build directory path: BASE/ProfileFolder/YYYY/MM.MMM/DD/NUMBER - HEADLINE
    year = dt.strftime('%Y')
    month = dt.strftime('%m. %b')  # e.g., "01. Jan"
    day = dt.strftime('%d')

    save_dir = Path(GDRIVE_BASE_PATH) / gdrive_subfolder / year / month / day / folder_name
    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"Saving images to: {save_dir}")

    for idx, image_url in enumerate(image_urls, start=1):
        try:
            # Download image
            response = requests.get(image_url, timeout=30)
            if response.status_code != 200:
                print(f"Failed to download image {idx}: {response.status_code}")
                continue

            # Open image with PIL
            img = Image.open(BytesIO(response.content))

            # Convert AVIF, WebP, or any format to JPG
            if img.mode in ('RGBA', 'LA', 'P'):
                # Convert to RGB for JPG
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Save as JPG
            save_path = save_dir / f"Image{idx}.jpg"
            img.save(save_path, 'JPEG', quality=90, optimize=True)

            saved_paths.append(str(save_path))
            print(f"Saved image {idx}: {save_path}")

        except Exception as e:
            print(f"Error saving image {idx} from {image_url}: {e}")
            continue

    return saved_paths
