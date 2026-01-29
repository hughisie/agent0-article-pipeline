import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from agent0_scanner import scan_articles
from agent0_translator import extract_headline_from_path, translate_headline_json, translate_headline_md
from agent0_utils import extract_article_no

from .db import get_conn
from .fingerprint import compute_fingerprint


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


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
    """Load English headline from cache or file. Returns empty string if not translated."""
    try:
        # First check cache
        with get_conn() as conn:
            row = conn.execute(
                "SELECT headline_en_gb FROM headline_cache WHERE file_path = ?",
                (str(path),),
            ).fetchone()
            if row and row["headline_en_gb"]:
                return row["headline_en_gb"]
        
        # Then check if file has been translated
        if path.suffix.lower() == ".json":
            try:
                content = path.read_text(encoding="utf-8").strip()
                if not content:
                    print(f"[WARNING] Empty JSON file during scan: {path}")
                    return ""
                data = json.loads(content)
                # Only return headline_en_gb if it exists and is different from original
                headline_en = data.get("headline_en_gb", "").strip()
                if headline_en:
                    return headline_en
                # File hasn't been translated yet - return empty to signal this
                return ""
            except json.JSONDecodeError as e:
                print(f"[WARNING] Invalid JSON during scan: {path} - {e}")
                return ""
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
    
    # Skip numbered duplicates from source (files ending with " 2.json", " 3.json", etc.)
    import re
    stem = path.stem  # filename without extension
    if re.search(r'\s+\d+$', stem):
        print(f"[SCAN] Skipping numbered duplicate: {path.name}")
        return False
    
    # Skip empty files
    try:
        if path.stat().st_size == 0:
            print(f"[SCAN] Skipping empty file: {path.name}")
            return False
    except OSError:
        pass
    
    return True


def scan_paths(paths: list[str], skip_duplicates: bool = True) -> list[ScanItem]:
    print(f"[SCAN] Starting file discovery in {len(paths)} path(s)...")
    all_paths = []
    for root in paths:
        print(f"[SCAN] Scanning directory: {root}")
        all_paths.extend(scan_articles(root))
    print(f"[SCAN] Found {len(all_paths)} total files")
    
    print(f"[SCAN] Filtering candidates...")
    all_paths = [path for path in all_paths if _is_scan_candidate(path)]
    print(f"[SCAN] {len(all_paths)} files passed candidate filter")

    print(f"[SCAN] Loading duplicate detection data from database...")
    processed = set()
    published = set()
    published_paths = set()
    with get_conn() as conn:
        # Check processed table
        rows = conn.execute("SELECT fingerprint FROM processed").fetchall()
        processed = {row["fingerprint"] for row in rows}
        print(f"[SCAN] Loaded {len(processed)} processed fingerprints")

        # Check published_articles table
        pub_rows = conn.execute("SELECT fingerprint, file_path FROM published_articles WHERE fingerprint IS NOT NULL").fetchall()
        published = {row["fingerprint"] for row in pub_rows if row["fingerprint"]}
        published_paths = {row["file_path"] for row in pub_rows if row["file_path"]}
        print(f"[SCAN] Loaded {len(published)} published fingerprints, {len(published_paths)} published paths")

    print(f"[SCAN] Processing articles and extracting headlines...")
    seen_names = set()
    seen_headlines = {}  # Map normalized headline to first file path
    items = []
    idx = 1
    for i, path in enumerate(sorted(all_paths, key=lambda p: str(p).lower()), 1):
        # Progress update every 10 files
        if i % 10 == 0:
            print(f"[SCAN] Processing article {i}/{len(all_paths)}...")
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
        
        # Auto-translate headline if not in English
        if not headline_en and headline_raw:
            # Check if headline looks like it needs translation (has Spanish/Catalan characters)
            import re
            needs_translation = bool(re.search(r'[áéíóúñüàèòïç]', headline_raw.lower()))
            if needs_translation:
                try:
                    from config import load_config
                    config = load_config()
                    api_key = config.get("DEEPSEEK_API_KEY", "")
                    
                    if api_key and path.suffix.lower() == ".json":
                        result = translate_headline_json(path, api_key=api_key)
                        headline_en = result.headline_en_gb
                        # Cache the translation
                        with get_conn() as conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO headline_cache (file_path, headline_en_gb, updated_at) VALUES (?, ?, ?)",
                                (str(path), headline_en, now_iso())
                            )
                        print(f"[SCAN] Auto-translated: {basename} -> {headline_en}")
                    elif api_key and path.suffix.lower() in {".md", ".markdown"}:
                        result = translate_headline_md(path, api_key=api_key)
                        headline_en = result.headline_en_gb
                        # Cache the translation
                        with get_conn() as conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO headline_cache (file_path, headline_en_gb, updated_at) VALUES (?, ?, ?)",
                                (str(path), headline_en, now_iso())
                            )
                        print(f"[SCAN] Auto-translated: {basename} -> {headline_en}")
                except Exception as e:
                    print(f"[SCAN] Translation failed for {basename}: {e}")
                    # Continue with raw headline if translation fails
        
        # Check for duplicate headlines (same content, different filename)
        if not is_duplicate and headline_raw:
            # Normalize headline for comparison (lowercase, remove extra spaces, remove trailing numbers)
            import re
            normalized = re.sub(r'\s+', ' ', headline_raw.lower().strip())
            normalized = re.sub(r'\s*\d+\s*$', '', normalized)  # Remove trailing numbers like " 2"
            
            if normalized in seen_headlines:
                is_duplicate = True
                duplicate_reason = f"duplicate headline (same as {seen_headlines[normalized]})"
                print(f"[SCAN] Duplicate headline detected: '{headline_raw}' in {basename} (matches {seen_headlines[normalized]})")
            else:
                seen_headlines[normalized] = basename
        
        # Detect language more accurately
        language = "unknown"
        if headline_en:
            # Has been translated
            language = "en"
        elif headline_raw:
            # Not translated yet - detect from raw headline
            import re
            if re.search(r'[áéíóúñü]', headline_raw.lower()):
                language = "es"  # Spanish
            elif re.search(r'[àèéíòóúïüç]', headline_raw.lower()):
                language = "ca"  # Catalan
            else:
                # Check if it looks like English
                english_words = {'the', 'and', 'for', 'with', 'from', 'to', 'in', 'on', 'at'}
                words = set(headline_raw.lower().split())
                if words & english_words:
                    language = "en"
                else:
                    language = "unknown"

        item = ScanItem(
            index=idx,
            file_path=str(path.resolve()),
            basename=basename,
            article_no=extract_article_no(path),
            headline_raw=headline_raw,
            headline_en_gb=headline_en or headline_raw,  # Show raw if not translated
            language=language,
            is_duplicate=is_duplicate,
            duplicate_reason=duplicate_reason,
            fingerprint=fingerprint,
        )
        if not (skip_duplicates and is_duplicate):
            items.append(item)
            idx += 1
    
    duplicates_found = len(all_paths) - len(items)
    print(f"[SCAN] ✓ Scan complete: {len(items)} articles ready, {duplicates_found} duplicates skipped")
    return items
