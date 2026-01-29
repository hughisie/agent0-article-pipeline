import json
import re
from dataclasses import dataclass

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
    return [
        f"That debate has been building for months — we covered it in <a href=\"{url}\">{anchor_text}</a>.",
        f"This follows the issues we reported in <a href=\"{url}\">{anchor_text}</a>.",
        f"The wider context is explained in our earlier piece on <a href=\"{url}\">{anchor_text}</a>.",
        f"We previously looked at the background in <a href=\"{url}\">{anchor_text}</a>.",
    ]


def weave_internal_links(content: str, related: list[dict], max_links: int = 3) -> tuple[str, WeaveReport]:
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
        if not body.endswith((".", "!", "?")):
            body = body + "."
        body = body + " " + sentence
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
        "You are an editor inserting internal links into an existing WordPress Gutenberg article.\n"
        "You must preserve all content and block comments exactly, only adding link sentences.\n"
        "Return ONLY valid JSON."
    )
    user_prompt = """
You will receive:
  1) Gutenberg content.
  2) A list of internal links to insert.

Rules:
  - Use each URL at most once.
  - Insert links inside existing <!-- wp:paragraph --> blocks only.
  - Do not insert links in headings or HTML blocks.
  - Do not remove or rewrite existing content.
  - Add a short, natural sentence that includes the anchor text with <a href="URL">anchor</a>.
  - Vary phrasing between links; do not repeat the same pattern.

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
    pattern = re.compile(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    seen = set()
    rebuilt = []
    cursor = 0
    for match in pattern.finditer(content):
        href = match.group(1)
        text = match.group(2)
        rebuilt.append(content[cursor:match.start()])
        if domain in href:
            if href in seen:
                rebuilt.append(text)
            else:
                rebuilt.append(match.group(0))
                seen.add(href)
        else:
            rebuilt.append(match.group(0))
        cursor = match.end()
    rebuilt.append(content[cursor:])
    return "".join(rebuilt)
