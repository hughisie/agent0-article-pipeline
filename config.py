import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def load_config() -> dict:
    """Load config from config.json or environment variables (for cloud deployment)"""
    config = {}
    
    # Try loading from file first
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    
    # Fallback to environment variables (for Google Cloud Run)
    env_keys = [
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "WP_BASE_URL",
        "WP_USERNAME",
        "WP_APPLICATION_PASSWORD",
        "GOOGLE_CLIENT_ID",
        "JWT_SECRET",
        "GOOGLE_ACCESS_TOKEN",
        "PROMPT_TRANSLATION_SYSTEM",
        "PROMPT_TRANSLATION_USER",
        "PROMPT_PRIMARY_SYSTEM",
        "PROMPT_PRIMARY_USER",
        "PROMPT_ARTICLE_SYSTEM",
        "PROMPT_ARTICLE_USER",
        "PROMPT_HEADLINE_SYSTEM",
        "PROMPT_HEADLINE_USER",
    ]
    
    for key in env_keys:
        env_val = os.getenv(key)
        if env_val and key not in config:
            config[key] = env_val
    
    return config


def save_config(config: dict) -> None:
    """Save config to file. Fails gracefully if filesystem is read-only (e.g., Cloud Run)."""
    try:
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    except (OSError, PermissionError) as e:
        # Cloud Run has read-only filesystem - config is in env vars anyway
        pass


def prompt_for_keys(existing: dict) -> dict:
    config = dict(existing)
    gemini_key = config.get("GEMINI_API_KEY")
    deepseek_key = config.get("DEEPSEEK_API_KEY")

    if not gemini_key:
        gemini_key = input("Enter GEMINI_API_KEY: ").strip()
    if not deepseek_key:
        deepseek_key = input("Enter DEEPSEEK_API_KEY (optional, press Enter to skip): ").strip()

    if gemini_key:
        config["GEMINI_API_KEY"] = gemini_key
    if deepseek_key:
        config["DEEPSEEK_API_KEY"] = deepseek_key

    save_config(config)
    return config


def prompt_for_wp_config(existing: dict) -> dict:
    config = dict(existing)
    base_url = config.get("WP_BASE_URL")
    username = config.get("WP_USERNAME")
    app_password = config.get("WP_APPLICATION_PASSWORD")

    if not base_url:
        base_url = input("Enter WP_BASE_URL (e.g. https://example.com): ").strip()
    if not username:
        username = input("Enter WP_USERNAME: ").strip()
    if not app_password:
        app_password = input("Enter WP_APPLICATION_PASSWORD: ").strip()

    if base_url:
        config["WP_BASE_URL"] = base_url
    if username:
        config["WP_USERNAME"] = username
    if app_password:
        config["WP_APPLICATION_PASSWORD"] = app_password

    save_config(config)
    return config
