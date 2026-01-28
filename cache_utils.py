import hashlib
import json
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent / "run_cache.json"


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def compute_file_hash(path: str) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def get_cached_result(file_hash: str) -> dict | None:
    cache = _load_cache()
    return cache.get(file_hash)


def set_cached_result(file_hash: str, payload: dict) -> None:
    cache = _load_cache()
    cache[file_hash] = payload
    _save_cache(cache)
