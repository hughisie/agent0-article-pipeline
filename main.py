import argparse
import json
import os
import subprocess
import sys
import tempfile
import random
import re
import requests
from datetime import datetime
from pathlib import Path

from article_writer import _normalise_unicode, generate_wp_article
from blocks_utils import (
    add_footer_cta,
    add_inline_image_block,
    enforce_intro_structure,
    finalise_source_credits,
    PROMO_BLOCK,
)
from cache_utils import compute_file_hash, get_cached_result, set_cached_result
from config import load_config, prompt_for_keys, prompt_for_wp_config
from file_loader import load_article
from gdrive_image_saver import save_images_to_gdrive
from publishing import create_publisher, PublishingError
from agent0_gui.profile_manager import get_active_profile, get_all_profile_prompts
from image_utils import build_alt_text, extract_image_urls_from_article
from llm_clients import LLMError
from markdown_builder import build_research_markdown
from primary_source_finder import find_primary_source
from primary_source_resolver import PrimarySourceResolver
from internal_link_selector import select_internal_links_deepseek, InternalLinkSelectionError
from seo_memory import load_used_keyphrases, save_used_keyphrase
from url_validator import validate_original_source_url
from translation_analysis import translate_and_analyse_article
from taxonomy_assigner import assign_tags_and_category, TaxonomyAssignmentError
from yoast_optimizer import optimise_for_yoast, YoastOptimizationError
from yoast_bridge_client import yoast_check_status, yoast_sync_post, YoastBridgeError
from link_validator import validate_and_delink_outbound_links
from tag_generator import generate_tags_from_article, TagGenerationError
from internal_link_weaver import (
    weave_internal_links,
    weave_internal_links_gemini,
    GeminiWeaveError,
    ensure_internal_links_present,
    enforce_unique_internal_links,
    count_internal_links,
)
from sitemap_client import fetch_post_urls_from_sitemap, filter_urls_by_category, SitemapError
from wordpress_client import (
    WordPressError,
    create_draft_post,
    create_wp_tag,
    get_recent_posts,
    get_posts_by_urls,
    get_user_id_by_username,
    get_wp_categories,
    get_wp_tags,
    update_post,
    upload_media_from_url,
)


# Minimum image size in bytes (30KB) - filter out tiny placeholders/icons
MIN_IMAGE_SIZE_BYTES = 30 * 1024


def _check_image_size(image_url: str, min_size: int = MIN_IMAGE_SIZE_BYTES) -> tuple[bool, int | None]:
    """
    Check if image URL points to an image >= min_size bytes.

    Returns (is_acceptable, size_in_bytes).
    - is_acceptable: True if image is >= min_size
    - size_in_bytes: Actual size or None if couldn't determine
    """
    # Skip data URIs - reject them (they're usually tiny placeholders)
    if image_url.startswith("data:"):
        return False, None

    try:
        # First try HEAD request to get Content-Length
        head_response = requests.head(image_url, timeout=10, allow_redirects=True)
        content_length = head_response.headers.get("Content-Length")

        if content_length:
            size = int(content_length)
            return size >= min_size, size

        # If no Content-Length in HEAD, do a streaming GET with range
        # to try to get the size without downloading everything
        get_response = requests.get(
            image_url,
            stream=True,
            timeout=10,
            headers={"Range": "bytes=0-0"},
            allow_redirects=True,
        )
        content_range = get_response.headers.get("Content-Range")
        if content_range and "/" in content_range:
            # Format: "bytes 0-0/total_size"
            total_size = content_range.split("/")[-1]
            if total_size.isdigit():
                size = int(total_size)
                return size >= min_size, size

        # Fallback: download and check size (less efficient)
        get_response = requests.get(image_url, timeout=15, allow_redirects=True)
        size = len(get_response.content)
        return size >= min_size, size

    except Exception as exc:
        print(f"Warning: Could not check image size for {image_url[:60]}...: {exc}")
        # If we can't check, allow it through
        return True, None


def _filter_images_by_size(image_urls: list[str], min_size: int = MIN_IMAGE_SIZE_BYTES) -> list[str]:
    """Filter image URLs to only include those >= min_size bytes."""
    filtered = []
    for url in image_urls:
        is_acceptable, size = _check_image_size(url, min_size)
        if is_acceptable:
            filtered.append(url)
            if size:
                print(f"Image accepted ({size / 1024:.1f}KB): {url[:60]}...")
        else:
            size_str = f"{size / 1024:.1f}KB" if size else "unknown size"
            print(f"Image skipped (too small: {size_str} < {min_size / 1024:.0f}KB): {url[:60]}...")
    return filtered


def _choose_model(config: dict) -> str:
    has_deepseek = bool(config.get("DEEPSEEK_API_KEY"))
    print("Select model for translation + extraction:")
    print("[1] Gemini 2.5 Pro")
    if has_deepseek:
        print("[2] DeepSeek (deepseek-chat)")

    while True:
        choice = input("Enter choice: ").strip()
        if choice == "1":
            return "gemini-2.5-pro"
        if choice == "2" and has_deepseek:
            return "deepseek"
        print("Invalid choice. Try again.")


def _prompt_article_path() -> str:
    while True:
        path = input("Enter path to article file (.json or .md): ").strip().strip("\"'").strip()
        if path:
            return path
        print("Please enter a valid path.")


def _open_editor_with_json(data: dict) -> dict:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name
    subprocess.call([editor, tmp_path])
    edited = Path(tmp_path).read_text(encoding="utf-8")
    return json.loads(edited)


def _review_analysis(article, model_choice: str, config: dict) -> dict:
    while True:
        try:
            analysis = translate_and_analyse_article(article, model_choice, config)
        except (LLMError, ValueError) as exc:
            print(f"Analysis failed: {exc}")
            retry = input("Retry? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(1)
            continue

        print("\nStructured analysis:\n")
        print(json.dumps(_normalise_unicode(analysis), indent=2, ensure_ascii=False))
        accept = input("\nDo you want to accept this analysis? (y/n): ").strip().lower()
        if accept == "y":
            return analysis

        print("Choose an option:")
        print("[1] Re-run analysis")
        print("[2] Edit JSON manually")
        print("[3] Cancel")
        choice = input("Enter choice: ").strip()
        if choice == "1":
            continue
        if choice == "2":
            try:
                return _open_editor_with_json(analysis)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"Failed to load edited JSON: {exc}")
                continue
        if choice == "3":
            sys.exit(0)


def _review_wp_article(original_article: dict, analysis: dict, primary: dict, related: dict | None, config: dict, is_rerun: bool) -> dict:
    while True:
        try:
            model = "gemini-2.5-pro"
            if is_rerun:
                model = "gemini-2.5-flash"
            article_payload = generate_wp_article(
                original_article=original_article,
                analysis=analysis,
                primary_source=primary,
                related_articles=related,
                model_name=model,
                api_keys=config,
            )
        except (LLMError, ValueError) as exc:
            print(f"Article generation failed: {exc}")
            retry = input("Retry? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(1)
            continue

        print("\nGenerated WordPress article JSON:\n")
        print(json.dumps(_normalise_unicode(article_payload), indent=2, ensure_ascii=False))
        accept = input("\nDo you want to accept this article? (y/n): ").strip().lower()
        if accept == "y":
            return article_payload

        print("Choose an option:")
        print("[1] Re-run generation")
        print("[2] Edit JSON manually")
        print("[3] Cancel")
        choice = input("Enter choice: ").strip()
        if choice == "1":
            continue
        if choice == "2":
            try:
                return _open_editor_with_json(article_payload)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"Failed to load edited JSON: {exc}")
                continue
        if choice == "3":
            sys.exit(0)


def _manual_primary_override(primary: dict) -> dict:
    if not primary:
        primary = {}
    primary_source = primary.get("primary_source", {})
    print("\nPrimary source is missing. You can paste an official URL to validate manually.")
    url = input("Paste primary source URL (or press Enter to skip): ").strip()
    if not url:
        return primary
    title = input("Title (optional): ").strip()
    publisher = input("Publisher guess (optional): ").strip()
    source_type = input("Type guess (optional): ").strip()
    confidence = input("Confidence 0-1 (optional): ").strip()

    try:
        confidence_value = float(confidence) if confidence else 0.4
    except ValueError:
        confidence_value = 0.4

    primary_source = {
        "url": url,
        "title": title or None,
        "publisher_guess": publisher or None,
        "type_guess": source_type or None,
        "confidence": confidence_value,
    }
    primary["primary_source"] = primary_source
    return primary


def _log_primary_source(
    article_path: str,
    article: dict,
    analysis: dict,
    primary: dict,
    profile_id: int | None = None
) -> None:
    """
    Log primary source information to profile-specific log file.

    Args:
        article_path: Path to the article file
        article: Article dictionary
        analysis: Analysis dictionary
        primary: Primary source dictionary
        profile_id: Optional profile ID for profile-specific logging
    """
    from agent0_gui.profile_manager import get_profile_directories

    # Get profile output directory
    if profile_id:
        directories = get_profile_directories(profile_id)
        log_path = directories["output_dir"] / "primary_source_log.jsonl"
    else:
        # Fallback to default location
        log_path = Path(__file__).resolve().parent / "primary_source_log.jsonl"

    entry = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "article_path": article_path,
        "article_title": article.get("title"),
        "source_url": article.get("source_url"),
        "core_topic": analysis.get("core_topic"),
        "primary_source": primary.get("primary_source"),
        "alternatives": primary.get("alternatives", []),
        "reasoning_summary": primary.get("reasoning_summary"),
    }
    try:
        # Ensure directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"Warning: failed to write primary source log: {exc}")


def _summarise_related(related: dict | None) -> None:
    if not related:
        print("- Related articles: none")
        return
    related_items = related.get("related", []) if isinstance(related, dict) else []
    if related_items:
        print(f"- Related articles: {len(related_items)}")
    else:
        print("- Related articles: none")


def _read_raw_markdown(path: Path) -> str | None:
    if path.suffix.lower() in {".md", ".markdown"}:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _finalize_content(
    content: str,
    article: dict,
    primary: dict,
    config: dict,
    platform: str = "wordpress",
    profile_name: str = None,
) -> tuple[str, dict]:
    final_content = add_footer_cta(content, platform=platform, profile_name=profile_name)
    final_content = finalise_source_credits(
        final_content,
        (article or {}).get("source_url"),
        primary,
    )
    allowed_urls = set()
    source_url = (article or {}).get("source_url")
    if source_url:
        allowed_urls.add(source_url)
    primary_source = (primary or {}).get("primary_source") or {}
    primary_url = primary_source.get("url")
    if primary_url:
        allowed_urls.add(primary_url)
    enabled = bool(config.get("VALIDATE_OUTBOUND_URLS", True))
    final_content, link_report = validate_and_delink_outbound_links(
        final_content,
        enabled=enabled,
        allowed_urls=allowed_urls,
        repair_enabled=True,
        api_keys=config,
    )
    return final_content, link_report


def _log_final_content(final_content: str, link_report: dict) -> None:
    tail = final_content[-400:] if final_content else ""
    source_count = final_content.count(">Source</a>") if final_content else 0
    original_count = final_content.count(">Link to original article</a>") if final_content else 0
    internal_count = count_internal_links(final_content or "")
    spacer_check = "not_applicable"
    if final_content and PROMO_BLOCK in final_content:
        promo_idx = final_content.find(PROMO_BLOCK) + len(PROMO_BLOCK)
        image_idx = final_content.find("<!-- wp:image", promo_idx)
        if image_idx != -1:
            spacer_idx = final_content.find("<!-- wp:spacer", promo_idx, image_idx)
            spacer_check = "ok" if spacer_idx != -1 else "missing"
    print(f"Final content length: {len(final_content or '')}")
    print(f"Source link count: {source_count}")
    print(f"Original article link count: {original_count}")
    print(f"Internal link count (barna.news): {internal_count}")
    print(f"Spacer before image after promo: {spacer_check}")
    print(f"Final content tail (last 400 chars):\n{tail}")
    if link_report:
        print(
            "Link validation summary: "
            f"{link_report.get('checked', 0)} checked, "
            f"{link_report.get('broken', 0)} broken, "
            f"{len(link_report.get('removed_links', []))} removed."
        )
        for action in link_report.get("removed_links", []):
            print(f"- Link removed: {action.get('url')} ({action.get('reason')})")
        print(f"LINK_VALIDATION_REPORT: {json.dumps(link_report, ensure_ascii=False)}")


def _fallback_related_from_recent(
    recent_posts: list[dict],
    analysis: dict,
    article: dict,
    max_links: int = 3,
) -> list[dict]:
    terms = " ".join(
        [
            analysis.get("core_topic") or "",
            article.get("title") or "",
        ]
    ).lower()
    tokens = {t for t in terms.replace("/", " ").replace("-", " ").split() if len(t) > 3}
    scored = []
    for post in recent_posts or []:
        haystack = " ".join(
            [
                (post.get("title") or ""),
                (post.get("excerpt") or ""),
            ]
        ).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score <= 0:
            continue
        scored.append((score, post))
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen = []
    seen = set()
    for _, post in scored:
        url = post.get("url")
        title = post.get("title")
        if not url or url in seen:
            continue
        seen.add(url)
        chosen.append(
            {
                "url": url,
                "title": title,
                "anchor_text": title,
                "why_relevant": "Matched core topic keywords.",
                "suggested_insertion": "mid",
                "style": "context",
            }
        )
        if len(chosen) >= max_links:
            break
    return chosen


def _sitemap_related_candidates(
    base_sitemap_url: str,
    base_url: str,
    username: str,
    application_password: str,
    category_choice: dict | None,
) -> list[dict]:
    if not base_sitemap_url:
        return []
    try:
        urls = fetch_post_urls_from_sitemap(base_sitemap_url, max_urls=500)
    except SitemapError as exc:
        print(f"Warning: sitemap fetch failed: {exc}")
        return []
    slug = (category_choice or {}).get("slug")
    name = (category_choice or {}).get("name")
    filtered_urls = filter_urls_by_category(urls, slug, name)
    return get_posts_by_urls(
        base_url=base_url,
        username=username,
        application_password=application_password,
        urls=filtered_urls,
        max_posts=120,
    )

def _normalise_tag_value(value: str | None) -> str:
    return (value or "").strip().lower()


def _find_tag_id(wp_tags: list[dict], name: str | None, slug: str | None = None) -> int | None:
    name_norm = _normalise_tag_value(name)
    slug_norm = _normalise_tag_value(slug)
    for tag in wp_tags or []:
        tag_name = _normalise_tag_value(tag.get("name"))
        tag_slug = _normalise_tag_value(tag.get("slug"))
        if name_norm and name_norm == tag_name:
            return tag.get("id")
        if slug_norm and slug_norm == tag_slug:
            return tag.get("id")
    return None


def detect_profile_from_path(file_path: str) -> dict | None:
    """
    Auto-detect profile from input file location.

    Checks if the file is in any profile's input directory and returns that profile.
    Returns None if no match is found.

    Args:
        file_path: Path to the article file

    Returns:
        Profile dictionary if found, None otherwise
    """
    from agent0_gui.profile_manager import get_all_profiles

    try:
        input_path = Path(file_path).resolve()
        profiles = get_all_profiles()

        for profile in profiles:
            # Get profile's input directory
            profile_input_dir = Path(__file__).parent / profile["input_dir"]
            profile_input_dir = profile_input_dir.resolve()

            try:
                # Check if file is in this profile's directory
                input_path.relative_to(profile_input_dir)
                return profile  # File is in this profile's directory
            except ValueError:
                # File is not in this profile's directory, try next
                continue

        return None  # No match found

    except Exception as e:
        print(f"Warning: Profile detection failed: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and research primary sources from articles.")
    parser.add_argument("--dry-run", action="store_true", help="Run translation only and print JSON.")
    parser.add_argument("--rerun-post-id", type=int, help="Update an existing WordPress post ID with final assembly.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM steps and reuse existing wp.json.")
    parser.add_argument("--debug-links", action="store_true", help="Print internal linking diagnostics.")
    parser.add_argument("--input-path", help="Path to an article file to process.")
    parser.add_argument(
        "--model-choice",
        choices=["gemini-2.5-pro", "deepseek"],
        help="Model choice override for translation + extraction.",
    )
    parser.add_argument("--non-interactive", action="store_true", help="Run with default choices and no prompts.")
    args = parser.parse_args()
    if args.non_interactive:
        import builtins
        sys.stdin = open(os.devnull)

        def _no_input(*_args, **_kwargs):
            raise RuntimeError("Non-interactive mode: input() is disabled.")

        builtins.input = _no_input

    config = load_config()
    if args.non_interactive:
        if not config.get("GEMINI_API_KEY"):
            print("GEMINI_API_KEY is required.")
            sys.exit(1)
    else:
        config = prompt_for_keys(config)
        if not config.get("GEMINI_API_KEY"):
            print("GEMINI_API_KEY is required.")
            sys.exit(1)

    if args.model_choice:
        model_choice = args.model_choice
    else:
        model_choice = (
            config.get("MODEL_TRANSLATION", "gemini-2.5-pro")
            if args.non_interactive
            else _choose_model(config)
        )
    if args.input_path:
        article_path = args.input_path
    else:
        article_path = "" if args.non_interactive else _prompt_article_path()
    if args.non_interactive and not article_path:
        print("Missing --input-path for non-interactive run.")
        sys.exit(1)
    file_hash = compute_file_hash(article_path)
    cached = get_cached_result(file_hash)
    is_rerun = cached is not None
    if is_rerun:
        print("\nRerun detected: using cached optimisations where possible.")

    try:
        article = load_article(article_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Failed to load article: {exc}")
        sys.exit(1)

    input_path = Path(article_path).expanduser()
    original_source_url = article.source_url
    if original_source_url:
        validated_source_url, source_reason = validate_original_source_url(original_source_url)
        if validated_source_url:
            if validated_source_url != original_source_url:
                print(f"Original source canonicalized: {validated_source_url}")
            article.source_url = validated_source_url
        else:
            print(f"Original source URL failed validation; link will be omitted. Reason: {source_reason}")
            article.source_url = None

    # Profile detection and publisher initialization
    detected_profile = detect_profile_from_path(article_path)
    if detected_profile:
        print(f"\n✓ Auto-detected profile: {detected_profile['name']}")
        profile = detected_profile
    else:
        # No match, use active profile
        from agent0_gui.profile_manager import get_active_profile
        profile = get_active_profile()
        if profile:
            print(f"\n✓ Using active profile: {profile['name']}")
        else:
            print("\nWarning: No profile found, using default WordPress configuration")
            profile = None

    # Load platform configuration and create publisher
    publisher = None
    profile_id = None
    platform_config = {}
    if profile:
        profile_id = profile["id"]
        try:
            platform_config = json.loads(profile.get("platform_config") or "{}")

            if platform_config:
                publisher = create_publisher(platform_config)
                print(f"✓ Using platform: {publisher.platform_name}")
            else:
                print("Warning: Profile has no platform configuration, falling back to config.json")
        except (json.JSONDecodeError, PublishingError, ValueError) as e:
            print(f"Warning: Failed to initialize publisher from profile: {e}")
            print("Falling back to config.json WordPress configuration")

    if args.rerun_post_id and args.skip_llm:
        wp_output_path = input_path.with_suffix(input_path.suffix + ".wp.json")
        if not wp_output_path.exists():
            print(f"Missing WordPress article JSON: {wp_output_path}")
            sys.exit(1)
        wp_article = json.loads(wp_output_path.read_text(encoding="utf-8"))
        final_content, link_report = _finalize_content(
            wp_article.get("wp_block_content", ""),
            article.to_dict(),
            {},
            config,
            platform=publisher.platform_name if publisher else "wordpress",
            profile_name=profile["name"] if profile else None,
        )
        wp_article["wp_block_content"] = final_content
        try:
            wp_output_path.write_text(
                json.dumps(_normalise_unicode(wp_article), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (OSError, PermissionError):
            # Cloud Run filesystem may be read-only
            pass
        _log_final_content(final_content, link_report)

        if not args.non_interactive:
            config = prompt_for_wp_config(config)
        missing = [
            key
            for key in ["WP_BASE_URL", "WP_USERNAME", "WP_APPLICATION_PASSWORD"]
            if not config.get(key)
        ]
        if missing:
            print("Missing WordPress credentials; cannot update draft.")
            sys.exit(1)

        wp_tags = []
        try:
            wp_tags = get_wp_tags(
                base_url=config["WP_BASE_URL"],
                username=config["WP_USERNAME"],
                application_password=config["WP_APPLICATION_PASSWORD"],
            )
        except WordPressError as exc:
            print(f"Warning: failed to fetch WordPress tags: {exc}")

        try:
            generated = generate_tags_from_article(article.to_dict(), wp_tags, api_keys=config)
            tag_ids = []
            tag_names = []
            for tag in generated:
                name = tag.get("name")
                if not name:
                    continue
                tag_id = _find_tag_id(wp_tags, name)
                if not tag_id:
                    try:
                        created_tag = create_wp_tag(
                            base_url=config["WP_BASE_URL"],
                            username=config["WP_USERNAME"],
                            application_password=config["WP_APPLICATION_PASSWORD"],
                            name=name,
                        )
                        tag_id = created_tag.get("id")
                        if created_tag.get("name"):
                            wp_tags.append(
                                {
                                    "id": created_tag.get("id"),
                                    "name": created_tag.get("name"),
                                    "slug": created_tag.get("slug"),
                                }
                            )
                    except WordPressError as exc:
                        print(f"Tag creation failed for {name}: {exc}")
                if tag_id:
                    tag_ids.append(tag_id)
                tag_names.append(name)
            if tag_ids:
                wp_article["tag_ids"] = tag_ids
            if tag_names:
                wp_article["tags"] = tag_names
        except TagGenerationError as exc:
            print(f"Warning: tag generation failed: {exc}")

        author_id = None
        for username in random.sample(["admin", "Barbara_Town", "Laia_Serra"], 3):
            try:
                author_id = get_user_id_by_username(
                    base_url=config["WP_BASE_URL"],
                    username=config["WP_USERNAME"],
                    application_password=config["WP_APPLICATION_PASSWORD"],
                    target_username=username,
                )
                if author_id:
                    break
            except WordPressError:
                continue

        media_id = None
        raw_markdown = _read_raw_markdown(input_path)
        image_urls = extract_image_urls_from_article(article.to_dict(), raw_markdown)
        featured_image_url = None
        if image_urls:
            alt_text = build_alt_text(wp_article.get("primary_keyword"), None)
            try:
                media_id, featured_image_url = upload_media_from_url(
                    base_url=config["WP_BASE_URL"],
                    username=config["WP_USERNAME"],
                    application_password=config["WP_APPLICATION_PASSWORD"],
                    image_url=image_urls[0],
                    alt_text=alt_text,
                )
                print(f"Uploaded featured image (media ID {media_id}, URL: {featured_image_url}).")
            except WordPressError as exc:
                print(f"Featured image upload failed: {exc}")
        try:
            updated = update_post(
                base_url=config["WP_BASE_URL"],
                username=config["WP_USERNAME"],
                application_password=config["WP_APPLICATION_PASSWORD"],
                post_id=int(args.rerun_post_id),
                meta=wp_article,
                media_id=media_id,
                author_id=author_id,
            )
            print("\nDraft updated:")
            print(f"- ID: {updated.get('id')}")
            print(f"- Link: {updated.get('link')}")
            try:
                post_id = int(updated.get("id"))
                sync_response = yoast_sync_post(
                    base_url=config["WP_BASE_URL"],
                    username=config["WP_USERNAME"],
                    application_password=config["WP_APPLICATION_PASSWORD"],
                    post_id=post_id,
                    focuskw=wp_article.get("primary_keyword"),
                    title=wp_article.get("meta_title"),
                    metadesc=wp_article.get("meta_description"),
                    opengraph_image=featured_image_url,
                    twitter_image=featured_image_url,
                    opengraph_image_id=media_id if featured_image_url else None,
                    twitter_image_id=media_id if featured_image_url else None,
                )
                print(f"Yoast sync succeeded: {sync_response}")
                status = yoast_check_status(
                    base_url=config["WP_BASE_URL"],
                    username=config["WP_USERNAME"],
                    application_password=config["WP_APPLICATION_PASSWORD"],
                    post_id=post_id,
                )
                print(f"Yoast status: {status}")
            except (TypeError, ValueError, YoastBridgeError) as exc:
                print(f"Yoast sync failed: {exc}")
        except (WordPressError, ValueError) as exc:
            print(f"Draft update failed: {exc}")
        return

    print("\n" + "=" * 80)
    print("STAGE 1: TRANSLATION & ANALYSIS")
    print("=" * 80)
    print(f"Model: {model_choice}")
    if article.title:
        print(f"Article: {article.title[:60]}..." if len(article.title) > 60 else f"Article: {article.title}")
    else:
        print(f"Article: (no title)")
    
    if args.non_interactive:
        analysis = translate_and_analyse_article(article, model_choice, config)
    else:
        analysis = _review_analysis(article, model_choice, config)
    
    print(f"✓ Translation complete")
    print(f"  - Language detected: {analysis.get('language_detected', 'N/A')}")
    print(f"  - Core topic: {analysis.get('core_topic', 'N/A')}")
    print(f"  - Artifact type: {analysis.get('original_artifact_type', 'N/A')}")

    if args.dry_run:
        print("\nDry run enabled; skipping primary source search.")
        print(json.dumps(_normalise_unicode(analysis), indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 80)
    print("STAGE 2: PRIMARY SOURCE FINDING")
    print("=" * 80)

    # Check if article has primary_source_url in metadata
    article_dict = article.to_dict()
    provided_primary_url = article_dict.get("primary_source_url")

    if provided_primary_url:
        print(f"Primary source URL provided in metadata: {provided_primary_url}")
        print(f"  - Skipping primary source search")
        primary = {
            "primary_source": {
                "url": provided_primary_url,
                "title": None,
                "publisher_guess": None,
                "type_guess": "provided_in_metadata",
                "confidence": 1.0,
            },
            "alternatives": [],
            "reasoning_summary": "Primary source URL provided in article metadata.",
        }
    elif is_rerun:
        print("Rerun detected: skipping primary source lookup.")
        primary = {
            "primary_source": {
                "url": None,
                "title": None,
                "publisher_guess": None,
                "type_guess": None,
                "confidence": 0.0,
            },
            "alternatives": [],
            "reasoning_summary": "Skipped on rerun.",
        }
    else:
        print("Searching for primary source...")
        print(f"  - Using Gemini 2.5 Flash with Google Search grounding")
        print(f"  - Article type: {analysis.get('original_artifact_type', 'unknown')}")
        print(f"  - Publisher guess: {analysis.get('probable_primary_publisher', 'unknown')}")

        try:
            primary = find_primary_source(article, analysis, config)
            print(f"✓ Primary source search complete")
        except LLMError as exc:
            print(f"✗ Primary source search failed: {exc}")
            primary = {
                "primary_source": {
                    "url": None,
                    "title": None,
                    "publisher_guess": None,
                    "type_guess": None,
                    "confidence": 0.0,
                },
                "alternatives": [],
                "reasoning_summary": "Primary source lookup failed; user chose to continue without one.",
            }


    primary_source = primary.get("primary_source", {}) if primary else {}
    print("\nPrimary source found (initial):")
    if primary_source.get('url'):
        print(f"  ✓ URL: {primary_source.get('url')}")
        print(f"  - Title: {primary_source.get('title', 'N/A')}")
        print(f"  - Confidence: {primary_source.get('confidence', 0):.2f}")
        print(f"  - Type: {primary_source.get('type_guess', 'N/A')}")
    else:
        print(f"  ✗ No primary source URL found")
        print(f"  - Confidence: {primary_source.get('confidence', 0):.2f}")

    if not primary_source.get("url") and not args.non_interactive:
        add_manual = input("\nAdd manual primary source? (y/n): ").strip().lower()

        if add_manual == "y":
            primary = _manual_primary_override(primary)
            primary_source = primary.get("primary_source", {}) if primary else {}

    resolver = PrimarySourceResolver(config)
    article_payload = article.to_dict()
    article_payload["_filename"] = input_path.name
    article_payload["_file_path"] = str(input_path)
    run_id = os.environ.get("AGENT0_RUN_ID")
    if run_id:
        article_payload["agent_run_id"] = run_id
    resolution = resolver.resolve(primary or {}, article_payload)
    if not resolution.resolved_url and not args.non_interactive:
        add_manual_after = input(
            "\nPrimary source failed validation. Add a manual primary source to retry? (y/n): "
        ).strip().lower()
        if add_manual_after == "y":
            primary = _manual_primary_override(primary)
            resolution = resolver.resolve(primary or {}, article_payload)
    if primary is None:
        primary = {"primary_source": {}}
    if resolution.resolved_url:
        primary.setdefault("primary_source", {})
        primary["primary_source"]["url"] = resolution.resolved_url
    else:
        primary.setdefault("primary_source", {})
        primary["primary_source"]["url"] = None
        primary["primary_source"]["confidence"] = 0.0
    primary["resolution_report"] = resolution.report

    def _strict_primary(config: dict) -> bool:
        value = config.get("PRIMARY_SOURCE_STRICT", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    if _strict_primary(config) and not resolution.resolved_url:
        print("\nPrimarySourceResolver: no valid primary source; continuing with fallback or unset source.")
        for attempt in resolution.report.get("candidates_tried", []):
            print(f"- Tried: {attempt.get('original_url')} -> {attempt.get('final_url')} ({attempt.get('reason')})")

    print("\n" + "=" * 80)
    print("STAGE 3: PRIMARY SOURCE VALIDATION")
    print("=" * 80)
    
    primary_source = primary.get("primary_source", {}) if primary else {}
    print("\nPrimary source (after validation):")
    if primary_source.get('url'):
        print(f"  ✓ VALIDATED URL: {primary_source.get('url')}")
        print(f"  - Title: {primary_source.get('title', 'N/A')}")
        print(f"  - Confidence: {primary_source.get('confidence', 0):.2f}")
        print(f"  - Type: {primary_source.get('type_guess', 'N/A')}")
        print(f"\n  → This URL will be linked in the article as the primary source")
    else:
        print(f"  ✗ NO VALID PRIMARY SOURCE")
        print(f"  - The article will be published without a primary source link")
        if resolution.report.get('candidates_tried'):
            print(f"  - Attempted {len(resolution.report.get('candidates_tried', []))} candidate URLs")

    if primary:
        _log_primary_source(str(input_path), article.to_dict(), analysis, primary, profile_id=profile_id)

    related_articles = None
    recent_posts = []
    internal_linking_enabled = False
    use_related = "y" if args.non_interactive else input("\nEnable internal linking with related stories? (y/n): ").strip().lower()
    if use_related == "y":
        if not args.non_interactive:
            config = prompt_for_wp_config(config)
        missing = [
            key
            for key in ["WP_BASE_URL", "WP_USERNAME", "WP_APPLICATION_PASSWORD"]
            if not config.get(key)
        ]
        if missing:
            print("Missing WordPress credentials; skipping related article lookup.")
        else:
            internal_linking_enabled = True
            try:
                if publisher:
                    recent_posts = publisher.get_recent_posts()
                else:
                    recent_posts = get_recent_posts(
                        base_url=config["WP_BASE_URL"],
                        username=config["WP_USERNAME"],
                        application_password=config["WP_APPLICATION_PASSWORD"],
                    )
                if args.debug_links:
                    print(f"- Recent posts fetched: {len(recent_posts)}")
            except (WordPressError, PublishingError) as exc:
                internal_linking_enabled = False
                print(f"Recent post fetch failed: {exc}")

    generate_article = "y" if args.non_interactive else input("\nGenerate WordPress article now? (y/n): ").strip().lower()
    wp_article = None

    
    if generate_article == "y":
        if args.non_interactive:
            # Get model preference from active profile
            model_name = "gemini-3-pro-preview"  # default
            try:
                active_profile = get_active_profile()
                if active_profile:
                    profile_prompts = get_all_profile_prompts(active_profile["id"])
                    # Check PROMPT_ARTICLE_SYSTEM or PROMPT_ARTICLE_USER for model preference
                    for key in ["PROMPT_ARTICLE_SYSTEM", "PROMPT_ARTICLE_USER"]:
                        if key in profile_prompts and isinstance(profile_prompts[key], dict):
                            model_name = profile_prompts[key].get("model", "gemini-3-pro-preview")
                            break
            except Exception:
                pass  # Fall back to default if profile fetch fails
            
            wp_article = generate_wp_article(
                original_article=article.to_dict(),
                analysis=analysis,
                primary_source=primary,
                related_articles=related_articles,
                model_name=model_name,
                api_keys=config,
            )
        else:
            wp_article = _review_wp_article(article.to_dict(), analysis, primary, related_articles, config, is_rerun)

        article_meta = {
            "meta_title": wp_article.get("meta_title"),
            "meta_description": wp_article.get("meta_description"),
            "primary_keyword": wp_article.get("primary_keyword"),
            "slug": wp_article.get("slug"),
            "tags": wp_article.get("tags"),
            "excerpt": wp_article.get("excerpt"),
        }
        taxonomy = None
        wp_categories = []
        wp_tags = []
        if not args.non_interactive:
            config = prompt_for_wp_config(config)
        missing = [
            key
            for key in ["WP_BASE_URL", "WP_USERNAME", "WP_APPLICATION_PASSWORD"]
            if not config.get(key)
        ]
        if missing:
            print("Missing WordPress credentials; skipping taxonomy assignment.")
        else:
            try:
                if publisher:
                    taxonomies = publisher.get_taxonomies()
                    wp_categories = [
                        {"id": t.id, "name": t.name, "slug": t.slug}
                        for t in taxonomies.get("categories", [])
                    ]
                    wp_tags = [
                        {"id": t.id, "name": t.name, "slug": t.slug}
                        for t in taxonomies.get("tags", [])
                    ]
                else:
                    wp_categories = get_wp_categories(
                        base_url=config["WP_BASE_URL"],
                        username=config["WP_USERNAME"],
                        application_password=config["WP_APPLICATION_PASSWORD"],
                    )
                    wp_tags = get_wp_tags(
                        base_url=config["WP_BASE_URL"],
                        username=config["WP_USERNAME"],
                        application_password=config["WP_APPLICATION_PASSWORD"],
                    )
                taxonomy = assign_tags_and_category(
                    article=article.to_dict(),
                    analysis=analysis,
                    primary_source=primary,
                    article_meta=article_meta,
                    wp_categories=wp_categories,
                    wp_tags=wp_tags,
                    model_name="deepseek-chat",
                    api_keys=config,
                )
            except (WordPressError, TaxonomyAssignmentError, LLMError) as exc:
                print(f"Taxonomy assignment failed: {exc}")

        # Category choice is derived from taxonomy assignment; no hidden defaults.
        category_choice = None
        if taxonomy and taxonomy.get("category") and taxonomy["category"].get("id"):
            category_choice = taxonomy["category"]
        if category_choice is None:
            print("Warning: taxonomy assignment produced no usable category; leaving category unset.")

        if category_choice:
            article_meta["category_id"] = category_choice.get("id")
            article_meta["category_name"] = category_choice.get("name")
            wp_article["category_id"] = article_meta.get("category_id")
            wp_article["category_name"] = article_meta.get("category_name")

        if taxonomy and taxonomy.get("tags"):
            article_meta["tags"] = [t.get("name") for t in taxonomy["tags"] if t.get("name")]
            wp_article["tags"] = article_meta.get("tags")
            wp_article["tags_struct"] = taxonomy.get("tags")
            wp_article["tag_ids"] = [t.get("id") for t in taxonomy.get("tags", []) if t.get("id")]

        related_list = []
        if internal_linking_enabled:
            if not config.get("DEEPSEEK_API_KEY"):
                print("Warning: DEEPSEEK_API_KEY missing; using keyword fallback for internal links.")
                related_articles = {"related": _fallback_related_from_recent(recent_posts, analysis, article.to_dict())}
            else:
                try:
                    # Use profile's sitemap URL if available, otherwise fall back to config
                    sitemap_url = platform_config.get("sitemap_url") or config.get("WP_SITEMAP_URL", "https://barna.news/sitemap.xml")

                    sitemap_candidates = _sitemap_related_candidates(
                        sitemap_url,
                        config["WP_BASE_URL"],
                        config["WP_USERNAME"],
                        config["WP_APPLICATION_PASSWORD"],
                        taxonomy.get("category") if taxonomy else None,
                    )
                    candidate_posts = sitemap_candidates or recent_posts
                    if args.debug_links:
                        print(f"- Sitemap candidates: {len(sitemap_candidates)}")
                        print(f"- Candidate posts passed to DeepSeek: {len(candidate_posts)}")
                    if candidate_posts:
                        related_articles = select_internal_links_deepseek(
                            article=article.to_dict(),
                            analysis=analysis,
                            candidates=candidate_posts,
                            api_keys=config,
                        )
                    else:
                        related_articles = {"related": []}
                except (InternalLinkSelectionError, WordPressError) as exc:
                    print(f"Related article selection failed: {exc}")
                    related_articles = {"related": []}
            if related_articles and not related_articles.get("related") and recent_posts:
                print("Warning: candidates available but no related links selected; using fallback.")
                related_articles["related"] = _fallback_related_from_recent(
                    recent_posts,
                    analysis,
                    article.to_dict(),
                )
                if args.debug_links:
                    print(f"- Fallback related links: {len(related_articles.get('related', []))}")
                    print(json.dumps(related_articles, indent=2, ensure_ascii=False))
            related_list = related_articles.get("related", []) if related_articles else []
            if args.debug_links and related_list:
                print(f"- Related links selected: {len(related_list)}")
                print(json.dumps(related_list, indent=2, ensure_ascii=False))
        if related_list:
            weave_report = None
            try:
                wp_article["wp_block_content"] = weave_internal_links_gemini(
                    wp_article.get("wp_block_content", ""),
                    related_list,
                    api_key=config["GEMINI_API_KEY"],
                )
                inserted = [
                    item.get("url")
                    for item in related_list
                    if item.get("url") and item.get("url") in (wp_article.get("wp_block_content") or "")
                ]
                weave_report = {"method": "gemini", "inserted": inserted}
            except (GeminiWeaveError, LLMError) as exc:
                print(f"Gemini link weaving failed; falling back to deterministic insert: {exc}")
                wp_article["wp_block_content"], weave_report = weave_internal_links(
                    wp_article.get("wp_block_content", ""),
                    related_list,
                )
            wp_article["wp_block_content"] = enforce_unique_internal_links(
                wp_article.get("wp_block_content", "")
            )
            if args.debug_links:
                if isinstance(weave_report, dict):
                    print(f"- Internal links inserted (Gemini): {len(weave_report.get('inserted', []))}")
                    print(json.dumps(weave_report.get("inserted", []), indent=2))
                else:
                    print(f"- Internal links inserted: {len(weave_report.inserted)}")
                    if weave_report.inserted:
                        print(json.dumps(weave_report.inserted, indent=2))
        else:
            weave_report = None

        used_keyphrases = load_used_keyphrases()
        try:
            optimised = optimise_for_yoast(
                article_meta=article_meta,
                wp_block_content=wp_article.get("wp_block_content", ""),
                used_keyphrases=used_keyphrases,
                api_keys=config,
            )
            wp_article = {**wp_article, **optimised}
            save_used_keyphrase(wp_article.get("primary_keyword") or "")
        except YoastOptimizationError as exc:
            print(f"Yoast optimisation failed: {exc}")
            wp_article["yoast_notes"] = f"Optimisation failed: {exc}"

        if related_list:
            wp_article["wp_block_content"], missing = ensure_internal_links_present(
                wp_article.get("wp_block_content", ""),
                related_list,
            )
            if missing:
                print(f"Warning: Yoast removed internal links; reinserted missing URLs: {missing}")
            wp_article["wp_block_content"] = enforce_unique_internal_links(
                wp_article.get("wp_block_content", "")
            )
            if args.debug_links:
                print(f"- Internal links in final content: {count_internal_links(wp_article.get('wp_block_content',''))}")
            if not any(item.get("url") in (wp_article.get("wp_block_content", "") or "") for item in related_list):
                print("Error: related links selected but none appear in final content; retrying weave once.")
                wp_article["wp_block_content"], _ = weave_internal_links(
                    wp_article.get("wp_block_content", ""),
                    related_list,
                )
                wp_article["wp_block_content"] = enforce_unique_internal_links(
                    wp_article.get("wp_block_content", "")
                )

        wp_article["wp_block_content"] = enforce_intro_structure(
            wp_article.get("wp_block_content", ""),
            wp_article.get("meta_title") or "",
            platform=publisher.platform_name if publisher else "wordpress",
        )
        raw_markdown = _read_raw_markdown(input_path)
        image_urls = extract_image_urls_from_article(article.to_dict(), raw_markdown)
        secondary_image_url = image_urls[1] if len(image_urls) > 1 else None
        if secondary_image_url:
            alt_text = build_alt_text(wp_article.get("primary_keyword"), analysis.get("core_topic"))
            spacer_height = 24
            try:
                spacer_height = int(config.get("IMAGE_SPACER_HEIGHT_PX", 24))
            except (TypeError, ValueError):
                spacer_height = 24
            wp_article["wp_block_content"] = add_inline_image_block(
                wp_article.get("wp_block_content", ""),
                secondary_image_url,
                alt_text,
                spacer_height=spacer_height,
            )

        final_content, link_report = _finalize_content(
            wp_article.get("wp_block_content", ""),
            article.to_dict(),
            primary,
            config,
            platform=publisher.platform_name if publisher else "wordpress",
            profile_name=profile["name"] if profile else None,
        )
        wp_article["wp_block_content"] = final_content
        _log_final_content(final_content, link_report)

        wp_output_path = input_path.with_suffix(input_path.suffix + ".wp.json")
        try:
            wp_output_path.write_text(
                json.dumps(_normalise_unicode(wp_article), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (OSError, PermissionError):
            # Cloud Run filesystem may be read-only
            pass

        print(f"\nSaved WordPress article JSON: {wp_output_path}")

        print("\nArticle summary:")

        print(f"- Meta title: {wp_article.get('meta_title')}")
        print(f"- Primary keyword: {wp_article.get('primary_keyword')}")
        print(f"- Slug: {wp_article.get('slug')}")
        print(f"- Primary source: {primary_source.get('url')}")
        if wp_article.get("yoast_notes"):
            print(f"- Yoast notes: {wp_article.get('yoast_notes')}")
        _summarise_related(related_articles)

        if args.non_interactive:
            publish = "y"
            print("\nCreating WordPress draft (non-interactive mode)...")
        else:
            publish = input("\nCreate WordPress draft now? (y/n): ").strip().lower()
        if publish == "y":
            if not args.non_interactive:
                config = prompt_for_wp_config(config)
            missing = [
                key
                for key in ["WP_BASE_URL", "WP_USERNAME", "WP_APPLICATION_PASSWORD"]
                if not config.get(key)
            ]
            if missing:
                print("Missing WordPress credentials; cannot publish draft.")
            else:
                author_id = None
                for username in random.sample(["Laia_Serra", "Barbara_Town", "admin"], 3):
                    try:
                        author_id = get_user_id_by_username(
                            base_url=config["WP_BASE_URL"],
                            username=config["WP_USERNAME"],
                            application_password=config["WP_APPLICATION_PASSWORD"],
                            target_username=username,
                        )
                        if author_id:
                            break
                    except WordPressError:
                        continue

                media_id = None
                featured_image_url = None
                if image_urls:
                    # Filter out images smaller than 30KB (placeholders/icons)
                    original_count = len(image_urls)
                    image_urls = _filter_images_by_size(image_urls)
                    if len(image_urls) < original_count:
                        print(f"Filtered {original_count - len(image_urls)} images below 30KB minimum.")

                if image_urls:
                    # Save images to Google Drive
                    try:
                        article_dict = article.to_dict()
                        article_date = article_dict.get("date_time", datetime.now().isoformat())
                        json_filename = Path(input_path).name
                        # Extract article number from filename
                        article_number = None
                        match = re.match(r'^(\d+)-', json_filename)
                        if match:
                            article_number = match.group(1)
                        # Get translated headline from wp_article (meta_title is the English headline)
                        translated_headline = wp_article.get("meta_title") if wp_article else None
                        saved_paths = save_images_to_gdrive(
                            image_urls,
                            article_date,
                            json_filename,
                            profile_id=profile_id,
                            translated_headline=translated_headline,
                            article_number=article_number,
                        )
                        if saved_paths:
                            print(f"Saved {len(saved_paths)} images to Google Drive.")
                    except Exception as exc:
                        print(f"Warning: Failed to save images to Google Drive: {exc}")

                    # Upload images to publishing platform
                    alt_text = build_alt_text(wp_article.get("primary_keyword"), analysis.get("core_topic"))
                    uploaded_ids = []
                    uploaded_urls = []

                    for image_url in image_urls:
                        try:
                            if publisher:
                                # Use publisher abstraction
                                media_result = publisher.upload_media(image_url, alt_text)
                                uploaded_id = media_result.media_id
                                uploaded_url = media_result.url
                            else:
                                # Fallback to WordPress client
                                uploaded_id, uploaded_url = upload_media_from_url(
                                    base_url=config["WP_BASE_URL"],
                                    username=config["WP_USERNAME"],
                                    application_password=config["WP_APPLICATION_PASSWORD"],
                                    image_url=image_url,
                                    alt_text=alt_text,
                                )
                            # Skip None results (e.g., from base64 data URIs)
                            if uploaded_id is not None:
                                uploaded_ids.append(uploaded_id)
                                uploaded_urls.append(uploaded_url)
                                print(f"Uploaded image (ID: {uploaded_id}, URL: {uploaded_url}).")
                            else:
                                print(f"Skipped image (invalid format): {image_url[:80]}...")
                        except (WordPressError, PublishingError) as exc:
                            print(f"Image upload failed for {image_url}: {exc}")
                    if uploaded_ids:
                        media_id = uploaded_ids[0]
                        featured_image_url = uploaded_urls[0] if uploaded_urls else None
                        print(f"Using featured image media ID {media_id}.")
                # Create tags or map existing IDs if needed
                if taxonomy:
                    tag_ids = []
                    tag_names = []

                    for tag in taxonomy.get("tags", []):
                        tag_id = tag.get("id")
                        tag_name = tag.get("name")

                        # Try to find existing tag
                        if not tag_id:
                            tag_id = _find_tag_id(wp_tags, tag_name, tag.get("slug"))

                        # Create tag if it doesn't exist
                        if not tag_id and tag_name:
                            try:
                                if publisher:
                                    # Use publisher abstraction
                                    taxonomy_item = publisher.create_taxonomy_item(tag_name, "tag")
                                    tag_id = taxonomy_item.id
                                    wp_tags.append({
                                        "id": taxonomy_item.id,
                                        "name": taxonomy_item.name,
                                        "slug": taxonomy_item.slug,
                                    })
                                else:
                                    # Fallback to WordPress client
                                    created_tag = create_wp_tag(
                                        base_url=config["WP_BASE_URL"],
                                        username=config["WP_USERNAME"],
                                        application_password=config["WP_APPLICATION_PASSWORD"],
                                        name=tag_name,
                                    )
                                    tag_id = created_tag.get("id")
                                    if created_tag.get("name"):
                                        wp_tags.append({
                                            "id": created_tag.get("id"),
                                            "name": created_tag.get("name"),
                                            "slug": created_tag.get("slug"),
                                        })
                            except (WordPressError, PublishingError) as exc:
                                print(f"Tag creation failed for {tag_name}: {exc}")
                                # Refresh tags and try to find it
                                try:
                                    if publisher:
                                        taxonomies = publisher.get_taxonomies()
                                        wp_tags[:] = [
                                            {"id": t.id, "name": t.name, "slug": t.slug}
                                            for t in taxonomies.get("tags", [])
                                        ]
                                    else:
                                        wp_tags[:] = get_wp_tags(
                                            base_url=config["WP_BASE_URL"],
                                            username=config["WP_USERNAME"],
                                            application_password=config["WP_APPLICATION_PASSWORD"],
                                        )
                                    tag_id = _find_tag_id(wp_tags, tag_name, tag.get("slug"))
                                except (WordPressError, PublishingError) as refresh_exc:
                                    print(f"Tag lookup failed for {tag_name}: {refresh_exc}")

                        if tag_id:
                            tag_ids.append(tag_id)
                        if tag_name:
                            tag_names.append(tag_name)

                    if tag_ids:
                        wp_article["tag_ids"] = tag_ids
                    if tag_names:
                        wp_article["tags"] = tag_names

                update_id = "" if args.non_interactive else input(
                    "\nUpdate existing draft ID (press Enter to create new): "
                ).strip()
                
                # Optimize metadata for Ghost if needed
                if publisher and publisher.platform_name == "Ghost":
                    from ghost_metadata import optimize_article_metadata_for_ghost
                    print("\n📝 Optimizing metadata for Ghost CMS...")
                    wp_article = optimize_article_metadata_for_ghost(wp_article)

                try:
                    if update_id:
                        if publisher:
                            # Use publisher abstraction
                            post_result = publisher.update_post(
                                post_id=update_id,
                                meta=wp_article,
                                featured_media_id=media_id,
                                author_id=author_id,
                            )
                            created = post_result.platform_specific
                        else:
                            # Fallback to WordPress client
                            created = update_post(
                                base_url=config["WP_BASE_URL"],
                                username=config["WP_USERNAME"],
                                application_password=config["WP_APPLICATION_PASSWORD"],
                                post_id=int(update_id),
                                meta=wp_article,
                                media_id=media_id,
                                author_id=author_id,
                            )
                        print("\n✓ Draft updated:")
                    else:
                        if publisher:
                            # Use publisher abstraction
                            post_result = publisher.create_draft_post(
                                meta=wp_article,
                                featured_media_id=media_id,
                                author_id=author_id,
                            )
                            created = post_result.platform_specific
                            print(f"\n✓ Draft created on {publisher.platform_name}:")
                        else:
                            # Fallback to WordPress client
                            created = create_draft_post(
                                base_url=config["WP_BASE_URL"],
                                username=config["WP_USERNAME"],
                                application_password=config["WP_APPLICATION_PASSWORD"],
                                meta=wp_article,
                                media_id=media_id,
                                author_id=author_id,
                            )
                            print("\n✓ Draft created:")

                    print(f"- ID: {created.get('id')}")
                    print(f"- Link: {created.get('link') or created.get('url')}")

                    # Yoast sync only for WordPress
                    if not publisher or publisher.platform_name == "WordPress":
                        try:
                            post_id = int(created.get("id"))
                            sync_response = yoast_sync_post(
                                base_url=config["WP_BASE_URL"],
                                username=config["WP_USERNAME"],
                                application_password=config["WP_APPLICATION_PASSWORD"],
                                post_id=post_id,
                                focuskw=wp_article.get("primary_keyword"),
                                title=wp_article.get("meta_title"),
                                metadesc=wp_article.get("meta_description"),
                                opengraph_image=featured_image_url,
                                twitter_image=featured_image_url,
                                opengraph_image_id=media_id if featured_image_url else None,
                                twitter_image_id=media_id if featured_image_url else None,
                            )
                            print(f"Yoast sync succeeded: {sync_response}")
                            status = yoast_check_status(
                                base_url=config["WP_BASE_URL"],
                                username=config["WP_USERNAME"],
                                application_password=config["WP_APPLICATION_PASSWORD"],
                                post_id=post_id,
                            )
                            print(f"Yoast status: {status}")
                        except (TypeError, ValueError, YoastBridgeError) as exc:
                            print(f"Yoast sync failed: {exc}")
                except (WordPressError, PublishingError, ValueError) as exc:
                    print(f"Draft publish failed: {exc}")

    markdown = build_research_markdown(article, analysis, primary)
    output_path = input_path.with_suffix(input_path.suffix + ".research.md")
    try:
        output_path.write_text(markdown, encoding="utf-8")
        print(f"\nSaved: {output_path}")
    except (OSError, PermissionError):
        # Cloud Run filesystem may be read-only
        print(f"\nSkipped saving research.md (read-only filesystem)")


if __name__ == "__main__":
    main()
