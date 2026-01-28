import json
from dataclasses import dataclass
from pathlib import Path

from agent0_scanner import scan_articles
from agent0_translator import extract_headline_from_path
from agent0_utils import extract_article_no

from .db import get_conn
from .fingerprint import compute_fingerprint


@dataclass
class ScanItem:
    index: int
    file_path: str
    basename: str
    article_no: str
    headline_raw: str
    headline_en_gb: str
    language: str
    is_duplicate: bool
    duplicate_reason: str | None
    fingerprint: str


def _load_headline_en(path: Path) -> str:
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT headline_en_gb FROM headline_cache WHERE file_path = ?",
                (str(path),),
            ).fetchone()
            if row and row["headline_en_gb"]:
                return row["headline_en_gb"]
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("headline_en_gb") or data.get("original_title") or data.get("title") or ""
        elif path.suffix.lower() in {".md", ".markdown"}:
            # Extract title from markdown frontmatter
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            if len(lines) >= 3 and lines[0].strip() == "---":
                for idx in range(1, min(20, len(lines))):
                    if lines[idx].strip() == "---":
                        break
                    if lines[idx].startswith("title:"):
                        return lines[idx].split(":", 1)[1].strip()
            return path.stem
        content = path.read_text(encoding="utf-8")
        headline, _ = extract_headline_from_path(path)
        return headline
    except (json.JSONDecodeError, OSError):
        return ""


def _is_scan_candidate(path: Path) -> bool:
    name = path.name.lower()
    # Accept both .json and .md/.markdown files
    is_json = name.endswith(".json")
    is_md = name.endswith(".md") or name.endswith(".markdown")

    if not (is_json or is_md):
        return False

    # Exclude specific patterns
    if name.endswith(".json.wp.json"):
        return False
    if name.endswith(".json.research.md"):
        return False
    if name in {
        "primary_source_log.jsonl",
        "primary_sources_registry.json",
        "used_keyphrases.json",
        "config.json",
    }:
        return False
    if ".research" in name:
        return False
    return True


def scan_paths(paths: list[str], skip_duplicates: bool = True) -> list[ScanItem]:
    all_paths = []
    for root in paths:
        all_paths.extend(scan_articles(root))
    all_paths = [path for path in all_paths if _is_scan_candidate(path)]

    processed = set()
    published = set()
    published_paths = set()
    with get_conn() as conn:
        # Check processed table
        rows = conn.execute("SELECT fingerprint FROM processed").fetchall()
        processed = {row["fingerprint"] for row in rows}

        # Check published_articles table
        pub_rows = conn.execute("SELECT fingerprint, file_path FROM published_articles WHERE fingerprint IS NOT NULL").fetchall()
        published = {row["fingerprint"] for row in pub_rows if row["fingerprint"]}
        published_paths = {row["file_path"] for row in pub_rows if row["file_path"]}

    seen_names = set()
    items = []
    idx = 1
    for path in sorted(all_paths, key=lambda p: str(p).lower()):
        basename = path.name
        path_str = str(path.resolve())
        fingerprint = compute_fingerprint(path)
        duplicate_reason = None
        is_duplicate = False

        if fingerprint in processed:
            is_duplicate = True
            duplicate_reason = "already processed"
        elif fingerprint in published:
            is_duplicate = True
            duplicate_reason = "already published to WordPress"
        elif path_str in published_paths:
            is_duplicate = True
            duplicate_reason = "already published (by path)"
        elif basename.lower() in seen_names:
            is_duplicate = True
            duplicate_reason = "duplicate filename"
        seen_names.add(basename.lower())

        headline_raw, _source = extract_headline_from_path(path)
        headline_en = _load_headline_en(path)
        language = "unknown"
        if headline_raw:
            language = "en" if headline_raw == headline_en else "unknown"

        item = ScanItem(
            index=idx,
            file_path=str(path.resolve()),
            basename=basename,
            article_no=extract_article_no(path),
            headline_raw=headline_raw,
            headline_en_gb=headline_en or headline_raw,
            language=language,
            is_duplicate=is_duplicate,
            duplicate_reason=duplicate_reason,
            fingerprint=fingerprint,
        )
        if not (skip_duplicates and is_duplicate):
            items.append(item)
            idx += 1
    return items
