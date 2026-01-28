import json
import re
from dataclasses import dataclass
from pathlib import Path

from agent0_utils import now_iso, sidecar_meta_path
from deepseek_client import call_deepseek_chat, DeepSeekError
from config import load_config
from llm_clients import LLMError, parse_json_response


class TranslationError(Exception):
    pass


@dataclass
class TranslationResult:
    path: Path
    headline_raw: str
    headline_en_gb: str
    language: str
    language_confidence: float
    translated: bool
    model: str
    headline_source: str


_SPANISH_HINTS = {
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "que",
    "por",
    "para",
    "con",
    "sobre",
}
_ENGLISH_HINTS = {"the", "and", "for", "with", "from", "city", "news", "taxi"}
_CATALAN_HINTS = {
    "el",
    "la",
    "els",
    "les",
    "de",
    "del",
    "amb",
    "sobre",
}

_LANG_HINTS = {
    "en": "en",
    "en-gb": "en",
    "english": "en",
    "es": "es",
    "es-es": "es",
    "spanish": "es",
    "ca": "ca",
    "cat": "ca",
    "catalan": "ca",
}
_LANG_THRESHOLD = 0.7


def needs_translation(lang_code: str | None) -> bool:
    if not lang_code:
        return True
    return not lang_code.lower().startswith("en")


def _infer_language_simple(text: str) -> tuple[str, float]:
    if not text:
        return "unknown", 0.0
    lower = text.lower()
    if re.search(r"[áéíóúñü]", lower):
        return "es", 0.8
    if re.search(r"[àèéíòóúïüç]", lower):
        return "ca", 0.8
    words = re.findall(r"\b[a-zàèéíòóúïüçñ]+\b", lower)
    if not words:
        return "unknown", 0.0
    spanish_hits = sum(1 for w in words if w in _SPANISH_HINTS)
    catalan_hits = sum(1 for w in words if w in _CATALAN_HINTS)
    english_hits = sum(1 for w in words if w in _ENGLISH_HINTS)
    if spanish_hits >= 2 and spanish_hits >= english_hits and spanish_hits >= catalan_hits:
        return "es", min(1.0, 0.5 + spanish_hits * 0.1)
    if catalan_hits >= 2 and catalan_hits >= english_hits and catalan_hits >= spanish_hits:
        return "ca", min(1.0, 0.5 + catalan_hits * 0.1)
    if english_hits >= 2 and english_hits >= spanish_hits and english_hits >= catalan_hits:
        return "en", min(1.0, 0.5 + english_hits * 0.1)
    if english_hits >= 1 and spanish_hits == 0 and catalan_hits == 0:
        return "en", 0.6
    return "unknown", 0.0


def detect_language_heuristic(text: str) -> tuple[str, float]:
    return _infer_language_simple(text)


def _detect_language_llm(text: str, api_key: str, model_name: str) -> tuple[str, float]:
    system_prompt = "You detect the language of a headline. Respond only with valid JSON."
    user_prompt = (
        "Identify the language of this headline.\n"
        "Return JSON only: {\"language\": \"en|es|ca|other\", \"confidence\": 0-1}\n\n"
        f"Headline:\n{text}"
    )
    raw = call_deepseek_chat(model_name, system_prompt, user_prompt, api_key)
    try:
        payload = parse_json_response(raw)
    except LLMError as exc:
        raise DeepSeekError(str(exc)) from exc
    lang = str(payload.get("language") or "other").lower()
    conf = payload.get("confidence")
    try:
        conf_val = float(conf)
    except (TypeError, ValueError):
        conf_val = 0.0
    return lang, conf_val


def _translate_headline(text: str, api_key: str, model_name: str) -> str:
    config = load_config()
    system_prompt = config.get("PROMPT_HEADLINE_SYSTEM") or (
        "You translate news headlines into British English (en-GB). "
        "Use British spelling: organise (not organize), colour (not color), centre (not center), etc. "
        "Return one line only, no quotes, no extra commentary."
    )
    user_prompt_template = config.get("PROMPT_HEADLINE_USER") or (
        "Translate the headline into British English (en-GB). Keep it newsy, "
        "preserve proper nouns, and do not add facts. "
        "Use British spelling conventions: -ise endings (organise, realise), -our endings (colour, favour), "
        "-re endings (centre, theatre), -ence endings (defence, offence).\n\n"
        "Headline:\n<HEADLINE>"
    )
    user_prompt = user_prompt_template.replace("<HEADLINE>", text)
    raw = call_deepseek_chat(model_name, system_prompt, user_prompt, api_key)
    line = raw.strip().splitlines()[0].strip()
    line = line.strip("\"'“”")
    line = re.sub(r"[!?\\.]{2,}$", "", line).strip()
    return line


def _headline_from_filename(path: Path) -> str:
    stem = path.stem
    # Strip number prefix with dash separator (e.g., "001-Title" -> "Title")
    if "-" in stem:
        prefix = stem.split("-", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            stem = stem.split("-", 1)[1]
    # Strip number prefix with underscore separator (e.g., "001_Title" -> "Title")
    elif "_" in stem:
        prefix = stem.split("_", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            stem = stem.split("_", 1)[1]
    # Convert remaining underscores and dashes to spaces
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def extract_headline_source(data: dict, path: Path) -> tuple[str, str]:
    for key in ["original_title", "title", "headline"]:
        value = data.get(key)
        if value:
            return str(value).strip(), key
    meta = data.get("meta") or {}
    if isinstance(meta, dict) and meta.get("title"):
        return str(meta.get("title")).strip(), "meta.title"
    fallback = _headline_from_filename(path)
    return fallback, "filename"


def headline_needs_translation(
    headline_raw: str,
    lang_hint: str | None,
    api_key: str,
    model_name: str,
) -> tuple[bool, str, float]:
    if lang_hint:
        normalised = _LANG_HINTS.get(lang_hint.strip().lower())
        if normalised == "en":
            return False, "en", 1.0
        if normalised in {"es", "ca"}:
            return True, normalised, 1.0

    try:
        from langdetect import detect_langs
    except Exception:
        detect_langs = None

    if detect_langs:
        try:
            langs = detect_langs(headline_raw)
            if langs:
                lang = langs[0].lang
                conf = langs[0].prob
                if lang in {"en", "es", "ca"} and conf >= _LANG_THRESHOLD:
                    return lang != "en", lang, conf
        except Exception:
            pass

    lang, conf = _infer_language_simple(headline_raw)
    if lang in {"en", "es", "ca"} and conf >= _LANG_THRESHOLD:
        return lang != "en", lang, conf

    lang, conf = _detect_language_llm(headline_raw, api_key, model_name)
    if lang in {"en", "es", "ca"} and conf >= 0.6:
        return lang != "en", lang, conf

    return True, lang if lang else "unknown", conf


def extract_headline_from_path(path: Path) -> tuple[str, str]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return extract_headline_source(data, path)
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip(), "md_h1"
    return _headline_from_filename(path), "filename"


def translate_headline_json(
    path: Path,
    api_key: str,
    model_name: str = "deepseek-chat",
    dry_run: bool = False,
) -> TranslationResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    headline, source_field = extract_headline_source(data, path)
    lang_hint = (data.get("original_language") or "").strip()
    try:
        needs_translate, lang_detected, lang_conf = headline_needs_translation(
            headline, lang_hint, api_key, model_name
        )
    except DeepSeekError as exc:
        raise TranslationError(str(exc)) from exc

    translated = False
    model_used = "none"
    headline_en = headline
    if needs_translate:
        try:
            headline_en = _translate_headline(headline, api_key, model_name)
            translated = True
            model_used = model_name
        except DeepSeekError as exc:
            raise TranslationError(str(exc)) from exc

    if not dry_run:
        data["headline_en_gb"] = headline_en
        data["agent0_headline_source_field"] = source_field
        data["agent0_language_detected"] = lang_detected
        data["agent0_language_confidence"] = round(float(lang_conf), 3)
        data["agent0_translated_at"] = now_iso()
        data["agent0_model"] = model_used
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return TranslationResult(
        path=path,
        headline_raw=headline,
        headline_en_gb=headline_en,
        language=lang_detected,
        language_confidence=float(lang_conf),
        translated=translated,
        model=model_used,
        headline_source=source_field,
    )


def translate_headline_md(
    path: Path,
    api_key: str,
    model_name: str = "deepseek-chat",
    dry_run: bool = False,
) -> TranslationResult:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if not match:
        raise TranslationError("No H1 headline found in markdown.")
    headline = match.group(1).strip()
    lang_hint = None
    try:
        needs_translate, lang_detected, lang_conf = headline_needs_translation(
            headline, lang_hint, api_key, model_name
        )
    except DeepSeekError as exc:
        raise TranslationError(str(exc)) from exc

    translated = False
    model_used = "none"
    headline_en = headline
    if needs_translate:
        try:
            headline_en = _translate_headline(headline, api_key, model_name)
            translated = True
            model_used = model_name
        except DeepSeekError as exc:
            raise TranslationError(str(exc)) from exc

    if not dry_run:
        updated = content[: match.start(1)] + headline_en + content[match.end(1) :]
        path.write_text(updated, encoding="utf-8")
        meta = {
            "headline_en_gb": headline_en,
            "agent0_headline_source_field": "md_h1",
            "agent0_language_detected": lang_detected,
            "agent0_language_confidence": round(float(lang_conf), 3),
            "agent0_translated_at": now_iso(),
            "agent0_model": model_used,
        }
        sidecar_meta_path(path).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return TranslationResult(
        path=path,
        headline_raw=headline,
        headline_en_gb=headline_en,
        language=lang_detected,
        language_confidence=float(lang_conf),
        translated=translated,
        model=model_used,
        headline_source="md_h1",
    )
