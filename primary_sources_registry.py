import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


REGISTRY_PATH = Path(__file__).resolve().parent / "primary_sources_registry.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_registry(entries: list[dict]) -> None:
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_article_ref(article_id: str | None, filename: str | None, run_id: str | None, date: str | None) -> dict:
    ref = {}
    if article_id:
        ref["id"] = str(article_id)
    if filename:
        ref["filename"] = filename
    if run_id:
        ref["run_id"] = str(run_id)
    if date:
        ref["date"] = date
    return ref


def update_registry(
    url: str,
    source_type: str,
    article_id: str | None,
    filename: str | None = None,
    run_id: str | None = None,
    date: str | None = None,
) -> None:
    if not url:
        return
    entries = load_registry()
    now = _now_iso()
    article_id = article_id or "unknown"
    article_ref = _build_article_ref(article_id, filename, run_id, date)
    for entry in entries:
        if entry.get("url") == url:
            entry["last_seen"] = now
            if article_id not in entry.get("article_ids", []):
                entry.setdefault("article_ids", []).append(article_id)
            if article_ref:
                refs = entry.setdefault("article_refs", [])
                if article_ref not in refs:
                    refs.append(article_ref)
            entry["source_type"] = source_type
            save_registry(entries)
            return
    entries.append(
        {
            "url": url,
            "first_seen": now,
            "last_seen": now,
            "source_type": source_type,
            "article_ids": [article_id],
            "article_refs": [article_ref] if article_ref else [],
        }
    )
    save_registry(entries)

def _days_ago(iso_value: str | None) -> int | None:
    if not iso_value:
        return None
    try:
        seen = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((datetime.now(timezone.utc) - seen).total_seconds() // 86400)


def filter_registry(domain: str | None = None, source_type: str | None = None) -> list[dict]:
    entries = load_registry()
    filtered = []
    for entry in entries:
        entry_domain = urlparse(entry.get("url", "")).netloc
        if domain and domain not in entry_domain:
            continue
        if source_type and entry.get("source_type") != source_type:
            continue
        enriched = dict(entry)
        enriched["domain"] = entry_domain
        enriched["usage_count"] = len(entry.get("article_refs") or entry.get("article_ids") or [])
        enriched["last_seen_days_ago"] = _days_ago(entry.get("last_seen"))
        filtered.append(enriched)
    return filtered
