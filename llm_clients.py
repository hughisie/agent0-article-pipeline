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


class ContentModerationError(LLMError):
    """Raised when content is blocked by AI safety filters."""
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

                # Check for content moderation blocking
                if "promptFeedback" in data and data["promptFeedback"].get("blockReason") == "PROHIBITED_CONTENT":
                    raise ContentModerationError(
                        f"Gemini blocked content due to safety filters: {data.get('promptFeedback', {})}"
                    )

                try:
                    # Standard response structure
                    candidate = data["candidates"][0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    
                    # Collect text from ALL parts (grounded search may have
                    # functionCall parts before/between text parts)
                    text_parts = []
                    if parts:
                        for part in parts:
                            if isinstance(part, dict) and "text" in part:
                                text_parts.append(part["text"])
                            elif isinstance(part, str):
                                text_parts.append(part)
                    
                    if text_parts:
                        return "\n".join(text_parts)
                    
                    # Fallback: check for grounded response with searchEntryPoint
                    if "groundingMetadata" in candidate:
                        grounding = candidate.get("groundingMetadata", {})
                        # Try to get rendered content from grounding
                        rendered = grounding.get("searchEntryPoint", {}).get("renderedContent", "")
                        if rendered:
                            return rendered
                    
                    # If we got here, try to extract any text we can find
                    if content:
                        if isinstance(content, str):
                            return content
                    
                    raise KeyError("No text found in response")
                    
                except (KeyError, IndexError, TypeError) as exc:
                    # Log the actual response structure for debugging
                    import json as json_module
                    print(f"  ⚠️ Gemini response debug: {json_module.dumps(data, indent=2)[:500]}")
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
class AnthropicClient:
    """Client for Anthropic Claude API (failover for content moderation issues)."""
    api_key: str
    model: str = "claude-sonnet-4-5-20250929"

    def generate(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model,
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=240)

                if response.status_code != 200:
                    error_msg = f"Anthropic API error: {response.status_code} {response.text}"
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        wait_time = 10 * (2 ** attempt)
                        print(f"⚠️  {error_msg}, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    raise LLMError(error_msg)

                data = response.json()
                try:
                    return data["content"][0]["text"]
                except (KeyError, IndexError) as exc:
                    raise LLMError(f"Unexpected Anthropic response: {exc}")

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 10 * (2 ** attempt)
                    print(f"⚠️  Anthropic API connection error, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Anthropic API failed after {max_retries} attempts")
                    raise LLMError(f"Anthropic API connection failed after {max_retries} retries: {e}")

        raise LLMError(f"Anthropic API failed after {max_retries} attempts") from last_error


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
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=90)
                
                if response.status_code != 200:
                    error_msg = f"DeepSeek API error: {response.status_code} {response.text}"
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        wait_time = 5 * (2 ** attempt)
                        print(f"⚠️  {error_msg}, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    raise LLMError(error_msg)
                
                data = response.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as exc:
                    raise LLMError(f"Unexpected DeepSeek response: {exc}")
                    
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, 
                    requests.exceptions.ChunkedEncodingError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 5 * (2 ** attempt)
                    print(f"⚠️  DeepSeek API connection error, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ DeepSeek API failed after {max_retries} attempts")
                    raise LLMError(f"DeepSeek API connection failed after {max_retries} retries: {e}")
        
        raise LLMError(f"DeepSeek API failed after {max_retries} attempts") from last_error


class LLMClient:
    def __init__(self, model_choice: str, api_keys: dict, enable_claude_failover: bool = True):
        self.model_choice = model_choice
        self.api_keys = api_keys
        self.enable_claude_failover = enable_claude_failover

    def generate(self, system_prompt: str, user_prompt: str, timeout: int = 240) -> str:
        """Generate content with configurable timeout and automatic failover.

        Args:
            system_prompt: System instruction
            user_prompt: User message
            timeout: Request timeout in seconds (default 240 for article generation)

        Returns:
            Generated content string

        Raises:
            ContentModerationError: If content is blocked and failover is disabled or fails
            LLMError: For other API errors
        """
        try:
            if self.model_choice == "gemini-2.5-pro":
                client = GeminiClient(api_key=self.api_keys["GEMINI_API_KEY"], model="gemini-2.5-pro")
                return client.generate(system_prompt, user_prompt, timeout=timeout)
            elif self.model_choice == "gemini-3-pro-preview":
                client = GeminiClient(api_key=self.api_keys["GEMINI_API_KEY"], model="gemini-3-pro-preview")
                return client.generate(system_prompt, user_prompt, timeout=timeout)
            elif self.model_choice == "deepseek":
                client = DeepSeekClient(api_key=self.api_keys["DEEPSEEK_API_KEY"])
                return client.generate(system_prompt, user_prompt)
            elif self.model_choice == "claude-sonnet-4.5":
                if "ANTHROPIC_API_KEY" not in self.api_keys:
                    raise ValueError("ANTHROPIC_API_KEY not found in config")
                client = AnthropicClient(api_key=self.api_keys["ANTHROPIC_API_KEY"])
                return client.generate(system_prompt, user_prompt)
            else:
                raise ValueError(f"Unsupported model choice: {self.model_choice}")

        except ContentModerationError as e:
            # Content was blocked by safety filters
            if self.enable_claude_failover and "ANTHROPIC_API_KEY" in self.api_keys:
                print(f"\n⚠️  Content blocked by {self.model_choice}: {str(e)[:100]}")
                print(f"🔄 Failing over to Claude Sonnet 4.5 for content moderation bypass...")

                client = AnthropicClient(api_key=self.api_keys["ANTHROPIC_API_KEY"])
                result = client.generate(system_prompt, user_prompt)
                print(f"✓ Claude Sonnet 4.5 successfully generated content")
                return result
            else:
                # Re-raise if failover is disabled or no Anthropic key
                raise


class GeminiSearchClient:
    def __init__(self, api_key: str):
        self.client = GeminiClient(api_key=api_key, model="gemini-2.5-flash")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # Use both Google Search and Google Maps grounding for comprehensive results
        tools = [{"google_search": {}}, {"google_maps": {}}]
        return self.client.generate(system_prompt, user_prompt, tools=tools, timeout=180)


@dataclass
class PerplexitySonarClient:
    """Client for Perplexity Sonar API - web-grounded search with citations."""
    api_key: str
    model: str = "sonar-pro"

    def generate(self, system_prompt: str, user_prompt: str, max_retries: int = 3, timeout: int = 60) -> str:
        url = "https://api.perplexity.ai/chat/completions"
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
            "temperature": 0.1,
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)

                if response.status_code != 200:
                    error_msg = f"Perplexity API error: {response.status_code} {response.text[:300]}"
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        wait_time = 5 * (2 ** attempt)
                        print(f"⚠️  {error_msg}, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    raise LLMError(error_msg)

                data = response.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                    # Perplexity returns citations in the response
                    citations = data.get("citations", [])
                    if citations:
                        # Append citations as metadata for the caller
                        content += "\n\n__CITATIONS__: " + json.dumps(citations)
                    return content
                except (KeyError, IndexError) as exc:
                    raise LLMError(f"Unexpected Perplexity response: {exc}")

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 5 * (2 ** attempt)
                    print(f"⚠️  Perplexity API error, retrying in {wait_time}s ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                raise LLMError(f"Perplexity API failed after {max_retries} retries: {e}")

        raise LLMError(f"Perplexity API failed after {max_retries} attempts") from last_error
