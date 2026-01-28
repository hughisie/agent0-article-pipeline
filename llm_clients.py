import json
import re
import time
import threading
from dataclasses import dataclass
from typing import Optional

import requests

# Global rate limiter for Gemini API to prevent overwhelming with parallel requests
_GEMINI_LOCK = threading.Lock()
_LAST_GEMINI_CALL = 0
_MIN_GEMINI_INTERVAL = 2.0  # Minimum 2 seconds between Gemini API calls


class LLMError(Exception):
    pass


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_json_response(text: str) -> dict:
    try:
        return _extract_json(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Failed to parse JSON response: {exc}")


@dataclass
class GeminiClient:
    api_key: str
    model: str

    def generate(self, system_prompt: str, user_prompt: str, tools: Optional[list] = None, timeout: int = 240, max_retries: int = 4) -> str:
        """Generate content with configurable timeout and retry logic.
        
        Args:
            system_prompt: System instruction
            user_prompt: User message
            tools: Optional list of tools (e.g., google_search)
            timeout: Request timeout in seconds (default 240 for article generation)
            max_retries: Maximum number of retry attempts (default 4)
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        }
        if tools:
            payload["tools"] = tools
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # Global rate limiting to prevent overwhelming API with parallel requests
                with _GEMINI_LOCK:
                    global _LAST_GEMINI_CALL
                    elapsed = time.time() - _LAST_GEMINI_CALL
                    if elapsed < _MIN_GEMINI_INTERVAL:
                        wait = _MIN_GEMINI_INTERVAL - elapsed
                        time.sleep(wait)
                    _LAST_GEMINI_CALL = time.time()
                
                response = requests.post(url, params=params, headers=headers, json=payload, timeout=timeout)
                
                if response.status_code != 200:
                    error_msg = f"Gemini API error: {response.status_code} {response.text}"
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        wait_time = 10 * (2 ** attempt)
                        print(f"⚠️  {error_msg}, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    raise LLMError(error_msg)
                
                data = response.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as exc:
                    raise LLMError(f"Unexpected Gemini response structure: {exc}")
                    
            except requests.exceptions.ReadTimeout as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 15 * (2 ** attempt)
                    print(f"⚠️  Gemini API timeout (>{timeout}s), retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Gemini API timeout after {max_retries} attempts")
                    raise LLMError(f"Gemini API timeout after {max_retries} retries") from e
                    
            except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 10 * (2 ** attempt)
                    print(f"⚠️  Gemini API connection error, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Gemini API failed after {max_retries} attempts")
                    raise LLMError(f"Gemini API connection failed after {max_retries} retries") from e
        
        raise LLMError(f"Gemini API failed after {max_retries} attempts") from last_error


@dataclass
class DeepSeekClient:
    api_key: str
    model: str = "deepseek-chat"

    def generate(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> str:
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=90)
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = 5 * (2 ** attempt)
                    print(f"⚠️  DeepSeek API timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ DeepSeek API timeout after {max_retries} attempts")
                    raise LLMError(f"DeepSeek API timeout after {max_retries} retries: {e}")
        
        if response.status_code != 200:
            raise LLMError(f"DeepSeek API error: {response.status_code} {response.text}")
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected DeepSeek response: {exc}")


class LLMClient:
    def __init__(self, model_choice: str, api_keys: dict):
        self.model_choice = model_choice
        self.api_keys = api_keys

    def generate(self, system_prompt: str, user_prompt: str, timeout: int = 240) -> str:
        """Generate content with configurable timeout.
        
        Args:
            system_prompt: System instruction
            user_prompt: User message
            timeout: Request timeout in seconds (default 240 for article generation)
        """
        if self.model_choice == "gemini-2.5-pro":
            client = GeminiClient(api_key=self.api_keys["GEMINI_API_KEY"], model="gemini-2.5-pro")
            return client.generate(system_prompt, user_prompt, timeout=timeout)
        if self.model_choice == "deepseek":
            client = DeepSeekClient(api_key=self.api_keys["DEEPSEEK_API_KEY"])
            return client.generate(system_prompt, user_prompt)
        raise ValueError("Unsupported model choice")


class GeminiSearchClient:
    def __init__(self, api_key: str):
        self.client = GeminiClient(api_key=api_key, model="gemini-2.5-flash")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        tools = [{"google_search": {}}]
        return self.client.generate(system_prompt, user_prompt, tools=tools, timeout=180)
