import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from llm_clients import GeminiClient, LLMError, parse_json_response


class GeminiWeaveError(Exception):
    pass

@dataclass
class WeaveReport:
    total_related: int
    inserted: list[dict]
    skipped: list[dict]
    fallback_inserted: bool


def _paragraph_blocks(content: str) -> list[dict]:
    pattern = re.compile(
        r"(<!--\s*wp:paragraph\s*-->\s*<p>)(.*?)(</p>\s*<!--\s*/wp:paragraph\s*-->)",
        re.DOTALL | re.IGNORECASE,
    )
    blocks = []
    for match in pattern.finditer(content):
        blocks.append(
            {
                "start": match.start(),
                "end": match.end(),
                "prefix": match.group(1),
                "body": match.group(2),
                "suffix": match.group(3),
            }
        )
    return blocks


def _has_anchor(text: str) -> bool:
    return bool(re.search(r"<a\s+[^>]*href=", text, re.IGNORECASE))


def _build_templates(url: str, anchor_text: str) -> list[str]:
    """Build varied, natural link sentences. NEVER use repetitive patterns."""
    # These templates should read naturally and vary significantly
    return [
        f'<a href="{url}">{anchor_text}</a>',  # Just the link - let it be woven naturally
        f'Read more: <a href="{url}">{anchor_text}</a>',
        f'See also: <a href="{url}">{anchor_text}</a>',
        f'Related: <a href="{url}">{anchor_text}</a>',
    ]


def weave_internal_links(content: str, related: list[dict], max_links: int = 2) -> tuple[str, WeaveReport]:
    related = [item for item in (related or []) if item.get("url") and item.get("anchor_text")]
    seen_urls = set()
    unique = []
    for item in related:
        url = item.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique.append(item)
        if len(unique) >= max_links:
            break
    related = unique
    report = WeaveReport(total_related=len(related), inserted=[], skipped=[], fallback_inserted=False)
    if not content or not related:
        return content, report

    blocks = _paragraph_blocks(content)
    if not blocks:
        return content, report

    preferred_indices = []
    if len(blocks) >= 1:
        preferred_indices.extend([0, 1] if len(blocks) > 1 else [0])
    if len(blocks) >= 3:
        preferred_indices.extend([2, 3])
    if len(blocks) >= 5:
        preferred_indices.extend([4, 5])
    preferred_indices = [idx for idx in preferred_indices if idx < len(blocks)]

    updated = content
    used_urls = set()
    insertions = []
    used_templates = set()
    for item in related:
        url = item.get("url")
        anchor = item.get("anchor_text")
        if url in used_urls:
            report.skipped.append({"url": url, "reason": "duplicate"})
            continue
        chosen_index = None
        for idx in preferred_indices:
            if idx >= len(blocks):
                continue
            if _has_anchor(blocks[idx]["body"]):
                continue
            chosen_index = idx
            break
        if chosen_index is None:
            continue
        templates = _build_templates(url, anchor)
        sentence = None
        for template in templates:
            if template not in used_templates:
                sentence = template
                used_templates.add(template)
                break
        if sentence is None:
            sentence = templates[0]
        body = blocks[chosen_index]["body"].rstrip()
        # Don't append sentences that break flow - just add a simple link reference
        # The link should be on its own line or naturally integrated
        if not body.endswith((".", "!", "?")):
            body = body + "."
        # Add link as a subtle reference, not a jarring sentence
        body = body + f' <a href="{url}">{anchor}</a>.'
        insertions.append({"index": chosen_index, "url": url, "anchor_text": anchor})
        blocks[chosen_index]["body"] = body
        used_urls.add(url)
        report.inserted.append({"url": url, "paragraph_index": chosen_index})
        if len(report.inserted) >= max_links:
            break

    if insertions:
        for block in reversed(blocks):
            rebuilt = f"{block['prefix']}{block['body']}{block['suffix']}"
            updated = updated[:block["start"]] + rebuilt + updated[block["end"] :]
    else:
        # Fallback: append a new paragraph block if no suitable paragraph was found.
        fallback = _build_templates(related[0]["url"], related[0]["anchor_text"])[0]
        paragraph = (
            "<!-- wp:paragraph -->\n"
            f"<p>{fallback}</p>\n"
            "<!-- /wp:paragraph -->\n"
        )
        updated = updated.rstrip() + "\n\n" + paragraph
        report.fallback_inserted = True
        report.inserted.append({"url": related[0]["url"], "paragraph_index": "appended"})

    return updated, report


def weave_internal_links_gemini(
    content: str,
    related: list[dict],
    api_key: str,
    model_name: str = "gemini-2.0-flash-exp",
) -> str:
    if not content or not related:
        return content
    system_prompt = (
        "You are an expert editor for a Barcelona/Catalonia English-language news website.\n"
        "Your task is to naturally weave internal links into an existing article.\n"
        "You must preserve ALL existing content exactly - only add link references.\n"
        "Return ONLY valid JSON."
    )
    user_prompt = """
You will receive:
  1) Gutenberg content (WordPress block format).
  2) A list of related articles to link to.

CRITICAL RULES:
  - NEVER just append a link at the end of a paragraph - THIS IS THE WORST MISTAKE
  - NEVER use the phrase "The city previously addressed similar concerns when" - BANNED
  - Links MUST be woven INTO existing sentences, not added as separate phrases
  - Only add 1-2 links maximum, and ONLY if they genuinely fit the context
  - If a link doesn't fit naturally, DON'T include it - return content unchanged

ABSOLUTELY FORBIDDEN (will be rejected):
  ❌ "...based on solar radiation exposure. Catalan exports to India." - JUST APPENDING A LINK
  ❌ "...aimed at the international market. AI-driven industrial transformation." - DANGLING LINK
  ❌ Any link that appears as a standalone phrase at the end of a paragraph
  ❌ Any link not grammatically integrated into an existing sentence

CORRECT link integration (link is PART of the sentence):
  ✓ "The company is expanding internationally, similar to <a href="URL">other Catalan firms exporting to India</a>."
  ✓ "This follows Barcelona's push for <a href="URL">AI-driven industrial transformation</a> in the tech sector."
  ✓ "The funding mirrors trends seen in <a href="URL">recent biotech investments</a> across Catalonia."

HOW TO INSERT CORRECTLY:
  1. Find a sentence where the related topic naturally fits
  2. MODIFY that sentence to include the link as part of its grammar
  3. The link text should flow as a natural part of the sentence
  4. If you cannot find a natural fit, return the content UNCHANGED

Return ONLY JSON in this exact shape:
{
  "content": "FULL_UPDATED_GUTENBERG_CONTENT"
}

GUTENBERG_CONTENT:
<CONTENT_HERE>

RELATED_LINKS:
<RELATED_HERE>
"""
    user_prompt = user_prompt.replace("<CONTENT_HERE>", content)
    user_prompt = user_prompt.replace("<RELATED_HERE>", json.dumps(related, ensure_ascii=False, indent=2))
    client = GeminiClient(api_key=api_key, model=model_name)
    raw = client.generate(system_prompt, user_prompt, timeout=180)
    try:
        payload = parse_json_response(raw)
    except LLMError as exc:
        raise GeminiWeaveError(str(exc)) from exc
    updated = payload.get("content")
    if not isinstance(updated, str) or not updated.strip():
        raise GeminiWeaveError("Gemini weaving returned empty content.")
    return updated


def ensure_internal_links_present(content: str, related: list[dict]) -> tuple[str, list[str]]:
    missing = []
    for item in related or []:
        url = item.get("url")
        if not url:
            continue
        if url not in content:
            missing.append(url)
    if not missing:
        return content, []
    updated, _ = weave_internal_links(content, related)
    return updated, missing


def count_internal_links(content: str, domain: str = "barna.news") -> int:
    pattern = re.compile(rf"https?://{re.escape(domain)}/[^\s\"'<>]+", re.IGNORECASE)
    return len(pattern.findall(content or ""))


def enforce_unique_internal_links(content: str, domain: str = "barna.news") -> str:
    if not content:
        return content

    def _is_internal_href(href: str) -> bool:
        parsed = urlparse(href)
        netloc = (parsed.netloc or "").lower().lstrip("www.")
        # Relative URLs are internal by definition in this context.
        if not netloc and (href.startswith("/") or not parsed.scheme):
            return True
        return netloc == domain.lower().lstrip("www.")

    def _normalize_internal_href(href: str) -> str:
        parsed = urlparse(href)
        netloc = (parsed.netloc or domain).lower().lstrip("www.")
        path = (parsed.path or "").rstrip("/")
        if not path:
            path = "/"
        return f"{netloc}{path}"

    pattern = re.compile(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    seen = set()
    rebuilt = []
    cursor = 0
    for match in pattern.finditer(content):
        href = match.group(1)
        text = match.group(2)
        rebuilt.append(content[cursor:match.start()])
        if _is_internal_href(href):
            normalized = _normalize_internal_href(href)
            if normalized in seen:
                rebuilt.append(text)
            else:
                rebuilt.append(match.group(0))
                seen.add(normalized)
        else:
            rebuilt.append(match.group(0))
        cursor = match.end()
    rebuilt.append(content[cursor:])
    return "".join(rebuilt)
