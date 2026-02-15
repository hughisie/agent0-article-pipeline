"""
Link Integrator - Phase 2 of Article Generation

This module handles the optional integration of internal links into articles
AFTER the article content has been generated.

Key Principles:
1. Only add links if they TRULY enhance the article
2. Links must be grammatically integrated into existing sentences
3. If no natural fit exists, return the article unchanged
4. Quality over quantity - 0 links is better than forced links
"""

import json
import re
from typing import Optional

from llm_clients import GeminiClient, LLMError, parse_json_response


class LinkIntegrationError(Exception):
    """Raised when link integration fails."""
    pass


def integrate_internal_links(
    content: str,
    related_articles: list[dict],
    api_key: str,
    model_name: str = "gemini-2.0-flash",
    max_links: int = 2,
) -> tuple[str, dict]:
    """
    Attempt to integrate internal links into an article.
    
    Args:
        content: The article content (Gutenberg blocks)
        related_articles: List of related articles with url, title, etc.
        api_key: Gemini API key
        model_name: Model to use
        max_links: Maximum number of links to add (default 1)
    
    Returns:
        Tuple of (updated_content, integration_report)
    """
    report = {
        "attempted": False,
        "links_added": 0,
        "reason": None,
        "original_length": len(content) if content else 0,
    }
    
    if not content or not related_articles:
        report["reason"] = "No content or no related articles provided"
        return content, report
    
    # Filter to only truly relevant articles
    relevant = _filter_relevant_articles(content, related_articles)
    
    if not relevant:
        report["reason"] = f"No related articles were relevant (had {len(related_articles)} candidates)"
        print(f"  [internal-links] 0/{len(related_articles)} candidates passed relevance filter")
        return content, report
    
    print(f"  [internal-links] {len(relevant)}/{len(related_articles)} candidates passed relevance filter")
    
    report["attempted"] = True
    report["candidates"] = len(relevant)
    
    # Attempt integration with strict quality rules
    try:
        updated, links_added = _attempt_integration(
            content, 
            relevant[:max_links],  # Only try to add max_links
            api_key, 
            model_name
        )
        
        # Validate the integration quality
        if links_added > 0:
            if _integration_is_natural(content, updated):
                report["links_added"] = links_added
                report["reason"] = "Links integrated successfully"
                return updated, report
            else:
                report["reason"] = "Integration rejected - links felt forced"
                return content, report
        else:
            report["reason"] = "LLM chose not to add any links"
            return content, report
            
    except Exception as e:
        report["reason"] = f"Integration error: {str(e)}"
        return content, report


def _filter_relevant_articles(content: str, related_articles: list[dict]) -> list[dict]:
    """
    Filter related articles to only those that are truly relevant.
    
    A related article is relevant if:
    1. Its topic overlaps with the article content
    2. It's not already linked in the content
    """
    relevant = []
    content_lower = content.lower()
    
    for article in related_articles:
        url = article.get("url", "")
        title = article.get("title", "")
        
        # Skip if already linked
        if url and url in content:
            continue
        
        # Check for topic overlap using keywords from title
        title_words = set(title.lower().split())
        # Remove common words
        stop_words = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was", "were"}
        title_keywords = title_words - stop_words
        
        # Count how many keywords appear in the content
        overlap_count = sum(1 for word in title_keywords if len(word) > 3 and word in content_lower)
        
        # Adaptive threshold: require fewer overlaps for short titles
        min_overlap = 1 if len(title_keywords) <= 4 else 2
        if overlap_count >= min_overlap:
            article["_relevance_score"] = overlap_count
            relevant.append(article)
    
    # Sort by relevance
    relevant.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
    
    return relevant


def _attempt_integration(
    content: str,
    articles: list[dict],
    api_key: str,
    model_name: str,
) -> tuple[str, int]:
    """
    Use LLM to attempt natural link integration.
    """
    client = GeminiClient(api_key=api_key, model=model_name)
    
    link_count = len(articles)
    system_prompt = f"""You are an expert editor at a Barcelona English-language news site. Your task is to integrate up to {link_count} internal link(s) to related stories on barna.news into this article.

CRITICAL RULES:
1. Each link MUST be grammatically integrated into an EXISTING sentence
2. DO NOT append links at the end of paragraphs
3. DO NOT add new sentences, clauses, or phrases just for the link
4. If you cannot find a natural place for a link, SKIP it
5. Spread links across different paragraphs (not all in one place)
6. Use the suggested anchor_text where possible, but adjust for grammar
7. Use format: <a href="URL">anchor text</a> (no target or rel attributes needed for internal links)

FORBIDDEN (will be rejected):
❌ "...solar radiation exposure. Catalan exports to India." - Dangling link
❌ "...international market. AI-driven transformation." - Appended phrase
❌ "Read more about X in our related story" - Generic lead-in
❌ Any link that appears as a standalone phrase

GOOD EXAMPLES (link woven into the sentence):
✓ "The company is expanding, mirroring a broader trend among <a href="...">Catalan firms increasing exports to India</a>."
✓ "This follows the city's ongoing push for <a href="...">AI-driven industrial transformation</a> in key sectors."
✓ "The disruption to <a href="...">Rodalies services across Barcelona</a> left thousands stranded."

Return ONLY valid JSON:
{{
  "content": "FULL_UPDATED_CONTENT",
  "links_added": NUMBER_OF_LINKS_ADDED,
  "integration_points": ["Description of where each link was added"]
}}"""

    articles_json = json.dumps([
        {"url": a.get("url"), "title": a.get("title"), "anchor_text": a.get("anchor_text")}
        for a in articles
    ], indent=2)
    
    user_prompt = f"""Integrate up to {link_count} link(s) from the list below into this article. Only add links where they fit NATURALLY into existing sentences.

ARTICLE CONTENT:
{content}

AVAILABLE LINKS (integrate as many as fit naturally, max {link_count}):
{articles_json}

Remember: Quality over quantity. Return content unchanged with links_added: 0 if no link fits naturally."""

    try:
        raw = client.generate(system_prompt, user_prompt, timeout=120)
        result = parse_json_response(raw)
        
        updated_content = result.get("content", content)
        links_added = result.get("links_added", 0)
        
        if not isinstance(updated_content, str) or not updated_content.strip():
            return content, 0
            
        return updated_content, links_added
        
    except Exception as e:
        raise LinkIntegrationError(f"LLM integration failed: {e}")


def _integration_is_natural(original: str, updated: str) -> bool:
    """
    Validate that the link integration is natural, not forced.
    
    Checks for:
    1. Dangling links (link as standalone phrase at end of paragraph)
    2. New sentences added just for the link
    3. Significant content changes beyond link insertion
    """
    if not updated or updated == original:
        return True  # No change is fine
    
    # Check for dangling links pattern: ". <a>text</a>."
    dangling_pattern = r'\.\s*<a\s+href=["\'][^"\']+["\'][^>]*>([^<]{3,50})</a>\s*\.'
    dangling_matches = re.findall(dangling_pattern, updated)
    
    for match in dangling_matches:
        # If this dangling link wasn't in the original, it's a forced addition
        if match not in original:
            return False
    
    # Check that the content length hasn't changed dramatically
    # (would indicate new sentences were added)
    original_len = len(original)
    updated_len = len(updated)
    
    # Allow up to 30% length increase (for link markup with multiple links)
    if updated_len > original_len * 1.30:
        return False
    
    return True


def should_add_links(content: str, related_articles: list[dict]) -> bool:
    """
    Quick check to determine if we should even attempt link integration.
    
    Returns False if:
    - Content is too short
    - No related articles provided
    - Content already has internal links
    """
    if not content or len(content) < 500:
        return False
    
    if not related_articles:
        return False
    
    # Check if content already has internal links (barna.news domain)
    internal_link_pattern = r'href=["\']https?://barna\.news/'
    if re.search(internal_link_pattern, content):
        # Already has internal links - only skip if already well-linked
        existing_count = len(re.findall(internal_link_pattern, content))
        if existing_count >= 3:
            return False
    
    return True
