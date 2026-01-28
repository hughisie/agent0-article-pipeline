import requests


class DeepSeekError(Exception):
    pass


def call_deepseek_chat(model: str, system_prompt: str, user_prompt: str, api_key: str) -> str:
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code != 200:
        raise DeepSeekError(f"DeepSeek API error: {response.status_code} {response.text}")
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise DeepSeekError(f"Unexpected DeepSeek response: {exc}")
