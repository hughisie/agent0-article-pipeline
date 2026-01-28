import json
from pathlib import Path

USED_KEYPHRASES_PATH = Path(__file__).resolve().parent / "used_keyphrases.json"


def load_used_keyphrases() -> list[str]:
    if not USED_KEYPHRASES_PATH.exists():
        return []
    try:
        data = json.loads(USED_KEYPHRASES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    return []


def save_used_keyphrase(keyphrase: str) -> None:
    phrase = keyphrase.strip()
    if not phrase:
        return
    existing = load_used_keyphrases()
    if phrase in existing:
        return
    existing.append(phrase)
    USED_KEYPHRASES_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
