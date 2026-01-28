import base64
import requests


class YoastBridgeError(Exception):
    pass


def _basic_auth_header(username: str, application_password: str) -> dict:
    token = f"{username}:{application_password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(token).decode("ascii")}


def yoast_sync_post(
    base_url: str,
    username: str,
    application_password: str,
    post_id: int,
    focuskw: str | None,
    title: str | None,
    metadesc: str | None,
    opengraph_image: str | None = None,
    twitter_image: str | None = None,
    opengraph_image_id: int | None = None,
    twitter_image_id: int | None = None,
) -> dict:
    """
    Calls the Barna Yoast Bridge endpoint to persist and reindex Yoast SEO data.
    """
    url = f"{base_url.rstrip('/')}/wp-json/barna/v1/yoast-sync"
    headers = {"Content-Type": "application/json"}
    headers.update(_basic_auth_header(username, application_password))
    payload = {
        "post_id": post_id,
        "focuskw": focuskw,
        "title": title,
        "metadesc": metadesc,
    }
    if opengraph_image:
        payload["opengraph-image"] = opengraph_image
        print(f"Setting OpenGraph image: {opengraph_image}")
    if twitter_image:
        payload["twitter-image"] = twitter_image
        print(f"Setting Twitter card image: {twitter_image}")
    if opengraph_image_id:
        payload["opengraph-image-id"] = opengraph_image_id
        print(f"Setting OpenGraph image ID: {opengraph_image_id}")
    if twitter_image_id:
        payload["twitter-image-id"] = twitter_image_id
        print(f"Setting Twitter card image ID: {twitter_image_id}")

    print(f"Yoast sync payload: {payload}")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise YoastBridgeError(f"Yoast sync failed: {response.status_code} {response.text}")

    result = response.json()
    print(f"Yoast sync response: {result}")
    return result


def yoast_check_status(
    base_url: str,
    username: str,
    application_password: str,
    post_id: int,
) -> dict:
    """
    Verifies that Yoast fields are stored and indexed for a post.
    """
    url = f"{base_url.rstrip('/')}/wp-json/barna/v1/yoast-status"
    headers = _basic_auth_header(username, application_password)
    params = {"post_id": post_id}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise YoastBridgeError(f"Yoast status failed: {response.status_code} {response.text}")
    return response.json()
