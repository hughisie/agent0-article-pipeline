import hashlib
import json
from pathlib import Path


def _tokenise(text: str) -> str:
    words = (text or "").strip().split()
    return " ".join(words[:5]).lower()


def compute_fingerprint(path: Path, data: dict | None = None) -> str:
    if data is None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    stable_id = data.get("id") or data.get("uuid") or data.get("guid")
    if stable_id:
        return hashlib.sha256(str(stable_id).encode("utf-8")).hexdigest()

    headline = data.get("headline_en_gb") or data.get("original_title") or data.get("title") or ""
    first_words = _tokenise(headline)
    date = data.get("date_time") or data.get("date") or ""
    name = path.name.lower()
    payload = f"{name}|{first_words}|{date}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
