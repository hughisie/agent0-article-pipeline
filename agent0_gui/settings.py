import json
from typing import Any

from config import load_config, save_config
import prompts


DEFAULT_SETTINGS = {
    "root_path": "/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/09. Feed Finder",
    "skip_duplicates": True,
    "primary_source_strict": True,
    "validate_outbound_urls": True,
    "enforce_image_spacing": True,
    "image_spacer_height_px": 24,
    "active_scan_root": None,
    "scan_mode": "upload",
}


def _prompt_map() -> dict:
    entries = {}
    for key in dir(prompts):
        if key.endswith("_SYSTEM") or key.endswith("_USER"):
            value = getattr(prompts, key)
            if isinstance(value, str):
                entries[key] = value
    return entries


def _apply_prompt_overrides(config: dict, prompts_map: dict) -> dict:
    updated = dict(prompts_map)
    for key, value in config.items():
        if key.startswith("PROMPT_OVERRIDE_"):
            prompt_key = key.replace("PROMPT_OVERRIDE_", "", 1)
            if prompt_key in updated and isinstance(value, str):
                updated[prompt_key] = value
    return updated


def _is_sensitive(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in ["API_KEY", "PASSWORD", "USERNAME", "APPLICATION_PASSWORD"])


STAGE_DISPLAY = {
    "translation": "Headline Translation",
    "primary_source": "Primary Source Finder",
    "article_writer": "Article Writer",
    "related_articles": "Internal Linking",
    "link_validation": "Link Validation",
    "publishing": "Publishing",
}


STAGE_ORDER = [
    "translation",
    "primary_source",
    "article_writer",
    "related_articles",
    "link_validation",
    "publishing",
]


def _stage_from_key(key: str) -> str:
    if "HEADLINE" in key:
        return "translation"
    if key.startswith("TRANSLATION"):
        return "translation"
    if key.startswith("PRIMARY"):
        return "primary_source"
    if key.startswith("RELATED"):
        return "related_articles"
    if key.startswith("ARTICLE"):
        return "article_writer"
    if key.startswith("LINK"):
        return "link_validation"
    if key.startswith("PUBLISH"):
        return "publishing"
    return "publishing"


def _display_name(stage_key: str) -> str:
    if stage_key in STAGE_DISPLAY:
        return STAGE_DISPLAY[stage_key]
    return stage_key.replace("_", " ").title()


def get_settings() -> dict[str, Any]:
    config = load_config()
    prompts_default = _prompt_map()
    prompts_current = _apply_prompt_overrides(config, prompts_default)

    settings = dict(DEFAULT_SETTINGS)
    settings["root_path"] = config.get("ROOT_PATH", settings["root_path"])
    settings["skip_duplicates"] = config.get("SKIP_DUPLICATES", settings["skip_duplicates"])
    settings["primary_source_strict"] = config.get("PRIMARY_SOURCE_STRICT", settings["primary_source_strict"])
    settings["validate_outbound_urls"] = config.get("VALIDATE_OUTBOUND_URLS", settings["validate_outbound_urls"])
    settings["image_spacer_height_px"] = config.get("IMAGE_SPACER_HEIGHT_PX", settings["image_spacer_height_px"])
    settings["enforce_image_spacing"] = config.get("ENFORCE_IMAGE_SPACING", True)
    settings["active_scan_root"] = config.get("ACTIVE_SCAN_ROOT")
    settings["scan_mode"] = config.get("SCAN_MODE", settings["scan_mode"])

    stages: dict[str, dict[str, Any]] = {}
    for key, value in config.items():
        if _is_sensitive(key):
            continue
        if (
            key.startswith("MODEL_")
            or key.startswith("TEMPERATURE_")
            or key.endswith("_STRICT")
            or (key.startswith("PROMPT_") and not key.startswith("PROMPT_OVERRIDE_"))
        ):
            base_key = (
                key.replace("MODEL_", "")
                .replace("TEMPERATURE_", "")
                .replace("PROMPT_", "")
            )
            stage = _stage_from_key(base_key)
            stages.setdefault(stage, {})[key] = value
    for key, value in prompts_current.items():
        stage = _stage_from_key(key)
        stages.setdefault(stage, {})[key] = value

    stage_defaults: dict[str, dict[str, Any]] = {}
    for key, value in prompts_default.items():
        stage = _stage_from_key(key)
        stage_defaults.setdefault(stage, {})[key] = value

    ordered = []
    for stage_key in STAGE_ORDER:
        if stage_key in stages or stage_key in stage_defaults:
            ordered.append(
                {
                    "key": stage_key,
                    "display_name": _display_name(stage_key),
                    "values": stages.get(stage_key, {}),
                    "defaults": stage_defaults.get(stage_key, {}),
                }
            )
    for stage_key in sorted(set(stages.keys()) - set(STAGE_ORDER)):
        ordered.append(
            {
                "key": stage_key,
                "display_name": _display_name(stage_key),
                "values": stages.get(stage_key, {}),
                "defaults": stage_defaults.get(stage_key, {}),
            }
        )

    settings["stages"] = ordered
    settings["stage_defaults"] = stage_defaults
    return settings


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    prompts_default = _prompt_map()
    for key, value in payload.items():
        if _is_sensitive(key):
            continue
        if key == "root_path":
            config["ROOT_PATH"] = value
            continue
        if key == "skip_duplicates":
            config["SKIP_DUPLICATES"] = bool(value)
            continue
        if key == "primary_source_strict":
            config["PRIMARY_SOURCE_STRICT"] = bool(value)
            continue
        if key == "validate_outbound_urls":
            config["VALIDATE_OUTBOUND_URLS"] = bool(value)
            continue
        if key == "enforce_image_spacing":
            config["ENFORCE_IMAGE_SPACING"] = bool(value)
            if not value:
                config["IMAGE_SPACER_HEIGHT_PX"] = 0
            elif config.get("IMAGE_SPACER_HEIGHT_PX", 0) == 0:
                config["IMAGE_SPACER_HEIGHT_PX"] = DEFAULT_SETTINGS["image_spacer_height_px"]
            continue
        if key == "image_spacer_height_px":
            config["IMAGE_SPACER_HEIGHT_PX"] = int(value)
            continue
        if key == "active_scan_root":
            config["ACTIVE_SCAN_ROOT"] = value
            continue
        if key == "scan_mode":
            config["SCAN_MODE"] = value
            continue
        if key in prompts_default:
            if value == prompts_default[key]:
                config.pop(f"PROMPT_OVERRIDE_{key}", None)
            else:
                config[f"PROMPT_OVERRIDE_{key}"] = value
            continue
        config[key] = value
    save_config(config)
    return get_settings()
