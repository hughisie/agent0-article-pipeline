import random
import re

FOOTER_CTA_BLOCKS_BARCELONA = [
    """<!-- wp:html -->
<p>
  Get all of the news delivered to your phone via our
  <a href="https://whatsapp.com/channel/0029Vb6PJDh6WaKjaAcWAX1h" target="_blank" rel="noopener">
    WhatsApp Broadcast Channel
  </a>.
</p>
<!-- /wp:html -->
""",
    """<!-- wp:html -->
<p>
  Join Barcelona English Speakers
  <a href="https://pocketbarcelona.com/community/main" target="_blank" rel="noopener">
    WhatsApp Community
  </a>.
</p>
<!-- /wp:html -->
""",
    """<!-- wp:html -->
<p>
  Apply to join our community of Entrepreneurs, Senior Executives and Founders at
  <a href="https://www.bizcelona.com/" target="_blank" rel="noopener">
    Bizcelona
  </a>.
</p>
<!-- /wp:html -->
""",
]

FOOTER_CTA_BLOCKS_RETROSHELL = [
    """<!-- wp:html -->
<p>
  Sign up to our SubStack and get all of the latest retro gaming news for the week delivered free to your inbox at the speed of Sonic every Monday at
  <a href="https://retrogamingnews.substack.com" target="_blank" rel="noopener">
    retrogamingnews.substack.com
  </a>.
</p>
<!-- /wp:html -->
""",
    """<!-- wp:html -->
<p>
  Get the worlds finest protection for your retro collection - visit our store to see our range of game display protectors at
  <a href="https://shop.retroshell.com/" target="_blank" rel="noopener">
    shop.retroshell.com
  </a>.
</p>
<!-- /wp:html -->
""",
]

# Backwards compatibility
FOOTER_CTA_BLOCKS = FOOTER_CTA_BLOCKS_BARCELONA


def add_footer_cta(content: str, platform: str = "wordpress", profile_name: str = None) -> str:
    """
    Add a footer CTA block based on platform and profile.

    Args:
        content: The article content
        platform: Publishing platform ("wordpress", "ghost", etc.)
        profile_name: Profile name to determine which CTA blocks to use

    Returns:
        Content with footer CTA appended
    """
    if not content:
        return content

    # Select appropriate CTA blocks based on profile
    if profile_name and "retro" in profile_name.lower():
        cta_blocks = FOOTER_CTA_BLOCKS_RETROSHELL
        check_urls = [
            "https://retrogamingnews.substack.com",
            "https://shop.retroshell.com/",
        ]
    else:
        cta_blocks = FOOTER_CTA_BLOCKS_BARCELONA
        check_urls = [
            "https://whatsapp.com/channel/0029Vb6PJDh6WaKjaAcWAX1h",
            "https://pocketbarcelona.com/community/main",
            "https://www.bizcelona.com/",
        ]

    # Check if CTA already exists
    if any(url in content for url in check_urls):
        return content

    block = random.choice(cta_blocks)
    return content.rstrip() + "\n\n" + block + "\n"


def maybe_append_source_link(
    content: str,
    article: dict,
    primary_source: dict,
    confidence_threshold: float = 0.6,
) -> str:
    """
    Append a Source link paragraph after the footer when no reliable primary source exists.
    """
    if not content:
        return content

    try:
        primary = (primary_source or {}).get("primary_source") or {}
        primary_url = (primary.get("url") or "").strip()
        confidence = float(primary.get("confidence") or 0.0)
    except (AttributeError, TypeError, ValueError):
        primary_url = ""
        confidence = 0.0

    if primary_url and confidence >= confidence_threshold:
        return content

    source_url = (article or {}).get("source_url") or ""
    source_url = source_url.strip()
    if not source_url:
        return content

    source_block = (
        "<p>\n"
        f"  <a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">\n"
        "    Source\n"
        "  </a>\n"
        "</p>\n"
    )
    return content.rstrip() + "\n\n" + source_block


def primary_source_is_reliable(primary_source: dict | None, threshold: float) -> bool:
    try:
        primary = (primary_source or {}).get("primary_source", {}) or {}
        url = (primary.get("url") or "").strip()
        conf = float(primary.get("confidence") or 0.0)
        return bool(url) and conf >= threshold
    except Exception:
        return False


def finalise_source_credits(
    content: str,
    source_url: str | None,
    primary_source: dict | None,
    confidence_threshold: float = 0.6,
) -> str:
    """
    Enforces end-of-article credits to be present EXACTLY ONCE.
    Removes any existing duplicates in ANY supported format, then appends the correct blocks once.

    Rules:
      - If we have a reliable primary source (confidence >= threshold), do NOT add "Link to original article"
      - If no reliable primary source, add "Link to original article" as fallback

    Args:
        content: Article content
        source_url: URL of the source article
        primary_source: Primary source dict with confidence
        confidence_threshold: Minimum confidence to consider primary source reliable

    Returns:
        Content with source credits finalized
    """
    if not content:
        return content
    source_url = (source_url or "").strip()
    if not source_url:
        return content

    def _remove_block(content_text: str, label: str) -> str:
        url = re.escape(source_url)
        label_pattern = re.escape(label)
        gutenberg = (
            r"<!--\s*wp:paragraph\s*-->\s*"
            r"<p>\s*<a[^>]*href=[\"']"
            + url
            + r"[\"'][^>]*>\s*"
            + label_pattern
            + r"\s*</a>\s*</p>\s*"
            r"<!--\s*/wp:paragraph\s*-->"
        )
        raw = (
            r"<p>\s*<a[^>]*href=[\"']"
            + url
            + r"[\"'][^>]*>\s*"
            + label_pattern
            + r"\s*</a>\s*</p>"
        )
        content_text = re.sub(gutenberg, "", content_text, flags=re.IGNORECASE | re.DOTALL)
        content_text = re.sub(raw, "", content_text, flags=re.IGNORECASE | re.DOTALL)
        return content_text

    # Remove any existing source credits
    content = _remove_block(content, "Source")
    content = _remove_block(content, "Link to original article")
    content = re.sub(r"\n{3,}", "\n\n", content).rstrip()

    # Check if we have a reliable primary source
    has_reliable_primary = primary_source_is_reliable(primary_source, confidence_threshold)

    # Only add "Link to original article" if we DON'T have a reliable primary source
    if not has_reliable_primary:
        blocks = [
            "<!-- wp:paragraph -->\n"
            f"<p><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener\">"
            "Link to original article</a></p>\n"
            "<!-- /wp:paragraph -->\n"
        ]
        return content + "\n\n" + "".join(blocks)

    return content


YOAST_BREADCRUMB_BLOCK = "<!-- wp:yoast-seo/breadcrumbs /-->\n"

PROMO_BLOCK = """<!-- wp:html -->
<a class="bnn-amazon-deals" href="https://whatsapp.com/channel/0029VbBd3cR5PO18Qtyxp22I" target="_blank" rel="noopener" style="display:block;transform-origin:center;">
  <video autoplay muted loop playsinline width="100%" style="border-radius:8px;display:block;transition:all 0.3s ease;">
    <source src="https://barna.news/wp-content/uploads/2025/11/Amazon-Broadcast-Channel.webm" type="video/webm">
    Your browser does not support the video tag.
  </video>
</a>

<style>
a.bnn-amazon-deals:hover video {
  filter: brightness(1.1);
  transform: scale(1.02);
}
</style>
<!-- /wp:html -->
"""


def _spacer_block(height_px: int) -> str:
    return (
        f"<!-- wp:spacer {{\"height\":\"{height_px}px\"}} -->\n"
        f"<div style=\"height:{height_px}px\" aria-hidden=\"true\" class=\"wp-block-spacer\"></div>\n"
        "<!-- /wp:spacer -->\n"
    )


def _last_block_name(content: str) -> str | None:
    idx = content.rfind("<!-- wp:")
    if idx == -1:
        return None
    end = content.find("-->", idx)
    if end == -1:
        return None
    snippet = content[idx:end]
    match = re.search(r"wp:([a-z0-9/_-]+)", snippet, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower()


def ensure_spacer_before_image(content: str, insert_at: int, height_px: int = 24) -> tuple[str, int]:
    before = content[:insert_at].rstrip()
    if not before:
        return content, insert_at
    if "<!-- wp:spacer" in before[-200:]:
        return content, insert_at
    last_block = _last_block_name(before)
    if last_block in {"html", "pattern", "image", "block"} or "bnn-amazon-deals" in before[-800:]:
        spacer = _spacer_block(height_px)
        content = content[:insert_at] + "\n\n" + spacer + "\n\n" + content[insert_at:]
        insert_at += len("\n\n" + spacer + "\n\n")
    return content, insert_at



def strip_h1_block(content: str) -> str:
    if not content:
        return content
    start = content.find("<!-- wp:heading {\"level\":1} -->")
    if start == -1:
        return content
    end = content.find("<!-- /wp:heading -->", start)
    if end == -1:
        return content
    end += len("<!-- /wp:heading -->")
    trimmed = content[:start] + content[end:]
    return trimmed.lstrip()
def _find_nth_paragraph_end(content: str, n: int) -> int | None:
    paragraph_block = "<!-- wp:paragraph -->"
    idx = -1
    for _ in range(n):
        idx = content.find(paragraph_block, idx + 1)
        if idx == -1:
            return None
    end_para = content.find("<!-- /wp:paragraph -->", idx)
    if end_para == -1:
        return None
    return end_para + len("<!-- /wp:paragraph -->")


def add_breadcrumb_block(content: str) -> str:
    if not content:
        return YOAST_BREADCRUMB_BLOCK
    if YOAST_BREADCRUMB_BLOCK in content:
        return content
    if PROMO_BLOCK in content:
        idx = content.find(PROMO_BLOCK) + len(PROMO_BLOCK)
        return content[:idx] + "\n" + YOAST_BREADCRUMB_BLOCK + content[idx:]
    end_second_para = _find_nth_paragraph_end(content, 2)
    if end_second_para is None:
        return YOAST_BREADCRUMB_BLOCK + content
    return content[:end_second_para] + "\n\n" + YOAST_BREADCRUMB_BLOCK + content[end_second_para:]


def add_promo_block(content: str, platform: str = "wordpress") -> str:
    """
    Add promo block (Amazon/WhatsApp) to WordPress articles only.

    Args:
        content: Article content
        platform: Publishing platform (skip promo for Ghost)

    Returns:
        Content with promo block added (WordPress only)
    """
    if not content:
        return content

    # Skip promo block for Ghost
    if platform and platform.lower() == "ghost":
        return content

    if PROMO_BLOCK in content:
        return content

    end_second_para = _find_nth_paragraph_end(content, 2)
    if end_second_para is None:
        return PROMO_BLOCK + content
    return content[:end_second_para] + "\n\n" + PROMO_BLOCK + "\n" + content[end_second_para:]


def add_inline_image_block(content: str, image_url: str, alt_text: str, spacer_height: int = 24) -> str:
    if not content or not image_url:
        return content
    image_block = (
        "<!-- wp:image {\"sizeSlug\":\"large\"} -->\n"
        f"<figure class=\"wp-block-image size-large\"><img src=\"{image_url}\" "
        f"alt=\"{alt_text}\" /></figure>\n"
        "<!-- /wp:image -->\n\n"
    )
    if PROMO_BLOCK in content:
        idx = content.find(PROMO_BLOCK) + len(PROMO_BLOCK)
        content, idx = ensure_spacer_before_image(content, idx, height_px=spacer_height)
        return content[:idx] + "\n" + image_block + content[idx:]
    end_second_para = _find_nth_paragraph_end(content, 2)
    if end_second_para is None:
        content, insert_at = ensure_spacer_before_image(content, 0, height_px=spacer_height)
        return image_block + content
    content, end_second_para = ensure_spacer_before_image(content, end_second_para, height_px=spacer_height)
    return content[:end_second_para] + "\n\n" + image_block + content[end_second_para:]


def strip_lede_title(content: str, headline: str) -> str:
    if not content or not headline:
        return content
    para_start = content.find("<!-- wp:paragraph -->")
    if para_start == -1:
        return content
    para_end = content.find("<!-- /wp:paragraph -->", para_start)
    if para_end == -1:
        return content
    block = content[para_start:para_end]
    if not block.lower().lstrip().startswith("<p>" + headline.lower()):
        return content
    stripped = block.replace(headline, "", 1).lstrip()
    # clean up leading punctuation/space after removal
    stripped = stripped.replace("<p> ", "<p>", 1)
    stripped = stripped.replace("<p>. ", "<p>", 1)
    stripped = stripped.replace("<p>, ", "<p>", 1)
    return content[:para_start] + stripped + content[para_end:]


def ensure_complimentary_lede(content: str, headline: str) -> str:
    """
    Originally intended to ensure first paragraph complements headline.
    Disabled to prevent injection of hardcoded text.
    """
    # Simply return content unchanged - do not inject any text
    return content


def ensure_two_paragraphs_before_h2(content: str, headline: str) -> str:
    if not content:
        return content
    h2_block = "<!-- wp:heading {\"level\":2} -->"
    idx = content.find(h2_block)
    if idx == -1:
        return content
    before = content[:idx]
    paragraph_count = before.count("<!-- wp:paragraph -->")
    if paragraph_count >= 2:
        return content

    extra = []
    if paragraph_count == 0:
        extra.append(
            "<!-- wp:paragraph -->\n"
            f"<p>{headline} sets the scene for the latest figures.</p>\n"
            "<!-- /wp:paragraph -->\n\n"
        )
    extra.append(
        "<!-- wp:paragraph -->\n"
        "<p>Here is what the newest data shows for the sector.</p>\n"
        "<!-- /wp:paragraph -->\n\n"
    )
    return "".join(extra) + content


def move_first_h2_after_intro(content: str) -> str:
    h2_block = "<!-- wp:heading {\"level\":2} -->"
    start = content.find(h2_block)
    if start == -1:
        return content
    end = content.find("<!-- /wp:heading -->", start)
    if end == -1:
        return content
    end += len("<!-- /wp:heading -->")

    insert_pos = _find_nth_paragraph_end(content, 2)
    if insert_pos is None:
        return content
    if PROMO_BLOCK in content:
        insert_pos = content.find(PROMO_BLOCK) + len(PROMO_BLOCK)
    if YOAST_BREADCRUMB_BLOCK in content:
        breadcrumb_end = content.find(YOAST_BREADCRUMB_BLOCK) + len(YOAST_BREADCRUMB_BLOCK)
        if breadcrumb_end > insert_pos:
            insert_pos = breadcrumb_end

    if start >= insert_pos:
        return content

    h2_block_text = content[start:end]
    before = content[:start]
    after = content[end:]
    content = before + after
    return content[:insert_pos] + "\n\n" + h2_block_text + content[insert_pos:]


def enforce_intro_structure(content: str, headline: str, platform: str = "wordpress") -> str:
    """
    Enforce article intro structure with platform-specific elements.

    Args:
        content: Article content
        headline: Article headline
        platform: Publishing platform (affects promo block inclusion)

    Returns:
        Content with enforced intro structure
    """
    content = strip_h1_block(content)
    content = strip_lede_title(content, headline)
    content = ensure_two_paragraphs_before_h2(content, headline)
    content = ensure_complimentary_lede(content, headline)
    content = add_promo_block(content, platform=platform)
    content = add_breadcrumb_block(content)
    content = move_first_h2_after_intro(content)
    return content
