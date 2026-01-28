import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

from config import load_config, prompt_for_wp_config
from yoast_bridge_client import yoast_check_status, yoast_sync_post, YoastBridgeError


def _basic_auth_header(username: str, application_password: str) -> dict:
    token = f"{username}:{application_password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(token).decode("ascii")}


def _latest_wp_json(root: Path) -> Path | None:
    candidates = list(root.glob("*.wp.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _fetch_latest_post_id(base_url: str, username: str, application_password: str) -> int:
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
    headers = _basic_auth_header(username, application_password)
    params = {"per_page": 1, "orderby": "date", "order": "desc", "status": "draft"}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch latest post: {response.status_code} {response.text}")
    data = response.json()
    if not data:
        raise RuntimeError("No posts returned from WordPress.")
    return int(data[0].get("id"))


def _fetch_post_id_by_title(
    base_url: str,
    username: str,
    application_password: str,
    title: str | None,
) -> int | None:
    if not title:
        return None
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
    headers = _basic_auth_header(username, application_password)
    params = {
        "per_page": 5,
        "orderby": "date",
        "order": "desc",
        "status": "draft",
        "search": title,
    }
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to search post by title: {response.status_code} {response.text}")
    data = response.json()
    if not data:
        return None
    return int(data[0].get("id"))


def main() -> None:
    config = prompt_for_wp_config(load_config())
    base_url = config.get("WP_BASE_URL")
    username = config.get("WP_USERNAME")
    application_password = config.get("WP_APPLICATION_PASSWORD")
    if not base_url or not username or not application_password:
        raise RuntimeError("Missing WordPress credentials in config.json.")

    latest_path = _latest_wp_json(Path.cwd())
    if not latest_path:
        raise RuntimeError("No .wp.json files found to load meta values.")

    data = json.loads(latest_path.read_text(encoding="utf-8"))
    focuskw = data.get("primary_keyword")
    title = data.get("meta_title")
    metadesc = data.get("meta_description")

    post_id = _fetch_post_id_by_title(base_url, username, application_password, title)
    if post_id is None:
        post_id = _fetch_latest_post_id(base_url, username, application_password)

    print(f"Using meta from {latest_path}")
    print(f"Latest WordPress post ID: {post_id}")
    print(f"Focus keyphrase: {focuskw}")
    print(f"Meta title: {title}")
    print(f"Meta description: {metadesc}")

    try:
        sync_response = yoast_sync_post(
            base_url=base_url,
            username=username,
            application_password=application_password,
            post_id=post_id,
            focuskw=focuskw,
            title=title,
            metadesc=metadesc,
        )
        print(f"Yoast sync response: {sync_response}")
        status = yoast_check_status(
            base_url=base_url,
            username=username,
            application_password=application_password,
            post_id=post_id,
        )
        print(f"Yoast status: {status}")
    except YoastBridgeError as exc:
        raise RuntimeError(f"Yoast sync failed: {exc}") from exc


if __name__ == "__main__":
    main()
