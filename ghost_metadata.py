"""
Ghost-specific metadata optimization.

Ghost has stricter metadata limits than WordPress:
- Meta title: max 60 characters (for Twitter cards)
- Meta description: max 145 characters (for social previews)
- Posts should be featured for visibility
"""


def truncate_smart(text: str, max_length: int) -> str:
    """
    Truncate text to max_length, trying to break at word boundaries.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text

    # Try to break at last space before max_length
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')

    if last_space > max_length * 0.8:  # If space is reasonably close to end
        return truncated[:last_space].strip()
    else:
        # No good break point, hard truncate
        return truncated.strip()


def optimize_meta_title_for_ghost(title: str) -> str:
    """
    Optimize meta title for Ghost (max 60 characters).

    Ghost uses meta title for:
    - Twitter cards (max 70 chars, but 60 is safer)
    - Facebook Open Graph
    - SEO

    Args:
        title: Original meta title

    Returns:
        Optimized title (max 60 chars)
    """
    if not title:
        return ""

    # Remove extra whitespace
    title = ' '.join(title.split())

    if len(title) <= 60:
        return title

    # Try to create a coherent short title
    truncated = truncate_smart(title, 60)

    # Ensure it's a complete sentence
    if truncated and not truncated[-1] in '.!?':
        # If we truncated mid-sentence, try to find a natural break
        if ':' in truncated:
            truncated = truncated.split(':')[0].strip()
        elif ' - ' in truncated:
            truncated = truncated.split(' - ')[0].strip()

    return truncated[:60]


def optimize_meta_description_for_ghost(description: str) -> str:
    """
    Optimize meta description for Ghost (max 145 characters).

    Ghost uses meta description for:
    - Twitter cards
    - Facebook Open Graph
    - Search engine snippets

    Args:
        description: Original meta description

    Returns:
        Optimized description (max 145 chars)
    """
    if not description:
        return ""

    # Remove extra whitespace
    description = ' '.join(description.split())

    if len(description) <= 145:
        return description

    # Truncate smartly
    truncated = truncate_smart(description, 145)

    # Ensure it ends with proper punctuation
    if truncated and not truncated[-1] in '.!?':
        # Add ellipsis if we truncated
        if len(truncated) <= 142:
            truncated += '...'
        else:
            truncated = truncated[:142] + '...'

    return truncated[:145]


def optimize_article_metadata_for_ghost(meta: dict) -> dict:
    """
    Optimize article metadata for Ghost CMS.

    Args:
        meta: Article metadata dictionary with meta_title, meta_description, etc.

    Returns:
        Updated metadata dictionary optimized for Ghost
    """
    optimized = meta.copy()

    # Optimize meta title (max 60 chars)
    if 'meta_title' in optimized:
        original_title = optimized['meta_title']
        optimized['meta_title'] = optimize_meta_title_for_ghost(original_title)

        if len(original_title) > 60:
            print(f"ℹ️  Meta title truncated for Ghost: {len(original_title)} → {len(optimized['meta_title'])} chars")
            print(f"   Original: {original_title}")
            print(f"   Optimized: {optimized['meta_title']}")

    # Optimize meta description (max 145 chars)
    if 'meta_description' in optimized:
        original_desc = optimized['meta_description']
        optimized['meta_description'] = optimize_meta_description_for_ghost(original_desc)

        if len(original_desc) > 145:
            print(f"ℹ️  Meta description truncated for Ghost: {len(original_desc)} → {len(optimized['meta_description'])} chars")
            print(f"   Original: {original_desc}")
            print(f"   Optimized: {optimized['meta_description']}")

    # Use meta_description as excerpt if not present
    if 'excerpt' not in optimized or not optimized['excerpt']:
        optimized['excerpt'] = optimized.get('meta_description', '')

    # Ensure tags exist (5-7 for Ghost)
    if 'tags' not in optimized or not optimized['tags']:
        optimized['tags'] = []
    elif len(optimized['tags']) > 7:
        print(f"ℹ️  Limiting tags to 7 for Ghost (was {len(optimized['tags'])})")
        optimized['tags'] = optimized['tags'][:7]

    return optimized
