import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests


ERROR_PATTERNS = [
    "404",
    "not found",
    "page not found",
    "no se encuentra",
    "no encontrada",
    "error 404",
    "document not found",
    "página no encontrada",
    "pagina no encontrada",
    "no s'ha trobat",
    "no encontrado",
]


@dataclass
class UrlValidationResult:
    original_url: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    content_length: int | None
    redirect_chain: list[str]
    ok: bool
    reason: str


def _has_error_signature(text: str) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in ERROR_PATTERNS)


def validate_url(
    url: str,
    expected_pdf: bool = False,
    timeout: int = 20,
    retries: int = 1,
) -> UrlValidationResult:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    last_exc: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_exc = str(exc)
            if attempt < retries:
                continue
            return UrlValidationResult(
                original_url=url,
                final_url=None,
                status_code=None,
                content_type=None,
                content_length=None,
                redirect_chain=[],
                ok=False,
                reason=f"request_error: {last_exc}",
            )

        redirect_chain = [resp.url for resp in response.history] if response.history else []
        status = response.status_code
        content_type = response.headers.get("Content-Type", "")
        content = response.text or ""
        length = len(response.content or b"")
        final_path = urlparse(response.url).path if response.url else ""
        original_path = urlparse(url).path if url else ""

        if status >= 500 and attempt < retries:
            continue

        if status >= 400:
            return UrlValidationResult(
                original_url=url,
                final_url=response.url,
                status_code=status,
                content_type=content_type,
                content_length=length,
                redirect_chain=redirect_chain,
                ok=False,
                reason=f"status_{status}",
            )

        if final_path in {"", "/", "/s/home.html"} and original_path not in {"", "/", "/s/home.html"}:
            return UrlValidationResult(
                original_url=url,
                final_url=response.url,
                status_code=status,
                content_type=content_type,
                content_length=length,
                redirect_chain=redirect_chain,
                ok=False,
                reason="redirected_to_home",
            )

        if expected_pdf or url.lower().endswith(".pdf"):
            if "pdf" not in content_type.lower():
                return UrlValidationResult(
                    original_url=url,
                    final_url=response.url,
                    status_code=status,
                    content_type=content_type,
                    content_length=length,
                    redirect_chain=redirect_chain,
                    ok=False,
                    reason="expected_pdf_but_not_pdf",
                )

        if response.url and "/not-found" in response.url:
            return UrlValidationResult(
                original_url=url,
                final_url=response.url,
                status_code=status,
                content_type=content_type,
                content_length=length,
                redirect_chain=redirect_chain,
                ok=False,
                reason="not_found_path",
            )

        if "text/html" in content_type.lower():
            sample = content[:2000]
            if _has_error_signature(sample):
                return UrlValidationResult(
                    original_url=url,
                    final_url=response.url,
                    status_code=status,
                    content_type=content_type,
                    content_length=length,
                    redirect_chain=redirect_chain,
                    ok=False,
                    reason="soft_404_signature",
                )
            if length < 400 and _has_error_signature(content):
                return UrlValidationResult(
                    original_url=url,
                    final_url=response.url,
                    status_code=status,
                    content_type=content_type,
                    content_length=length,
                    redirect_chain=redirect_chain,
                    ok=False,
                    reason="soft_404_short_html",
                )

        return UrlValidationResult(
            original_url=url,
            final_url=response.url,
            status_code=status,
            content_type=content_type,
            content_length=length,
            redirect_chain=redirect_chain,
            ok=True,
            reason="ok",
        )

    return UrlValidationResult(
        original_url=url,
        final_url=None,
        status_code=None,
        content_type=None,
        content_length=None,
        redirect_chain=[],
        ok=False,
        reason="unknown_error",
    )


def _strip_tracking(url: str) -> str:
    parsed = urlparse(url.strip())
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {}
    for key, value in params.items():
        lower = key.lower()
        if lower.startswith("utm_") or lower in {"fbclid", "gclid", "yclid", "igshid"}:
            continue
        cleaned[key] = value
    query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=query, fragment=""))


def _canonicalize_x_url(url: str) -> list[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    candidates = []
    if "twitter.com" in host or "x.com" in host:
        parts = [p for p in path.split("/") if p]
        status_id = None
        username = None
        if "status" in parts:
            status_idx = parts.index("status")
            if status_idx > 0:
                username = parts[status_idx - 1]
            if len(parts) > status_idx + 1:
                status_id = parts[status_idx + 1]
        if "i" in parts and "web" in parts and "status" in parts:
            status_idx = parts.index("status")
            if len(parts) > status_idx + 1:
                status_id = parts[status_idx + 1]
        if status_id and username:
            candidates.append(f"https://x.com/{username}/status/{status_id}")
            candidates.append(f"https://twitter.com/{username}/status/{status_id}")
        if status_id:
            candidates.append(f"https://x.com/i/web/status/{status_id}")
            candidates.append(f"https://twitter.com/i/web/status/{status_id}")
    return list(dict.fromkeys(candidates))


def validate_original_source_url(url: str) -> tuple[str | None, str]:
    if not url:
        return None, "missing"
    normalized = _strip_tracking(url)
    if normalized.startswith("http://"):
        normalized = "https://" + normalized[len("http://") :]
    candidates = [normalized]
    candidates.extend(_canonicalize_x_url(normalized))
    for candidate in candidates:
        result = validate_url(candidate)
        if result.ok:
            return result.final_url or candidate, "ok"
    return None, "validation_failed"
