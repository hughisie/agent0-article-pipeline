import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from config import load_config
from llm_clients import GeminiSearchClient, LLMError
from primary_sources_registry import update_registry


class UrlValidationResult:
    def __init__(
        self,
        original_url: str,
        final_url: str | None,
        status_code: int | None,
        content_type: str | None,
        content_length: int | None,
        redirect_chain: list[str],
        ok: bool,
        reason: str,
    ) -> None:
        self.original_url = original_url
        self.final_url = final_url
        self.status_code = status_code
        self.content_type = content_type
        self.content_length = content_length
        self.redirect_chain = redirect_chain
        self.ok = ok
        self.reason = reason


def _strip_tracking_params(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {}
    for key, value in params.items():
        if key.lower().startswith("utm_"):
            continue
        if key.lower() in {"fbclid", "gclid", "yclid", "igshid"}:
            continue
        cleaned[key] = value
    query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=query))


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if url.startswith("view-source:"):
        url = url.replace("view-source:", "", 1)
    url = _strip_tracking_params(url)
    parsed = urlparse(url)
    if parsed.scheme == "http":
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed)


def _amp_variants(url: str) -> list[str]:
    parsed = urlparse(url)
    path = parsed.path
    variants = []
    if path.endswith("/amp"):
        variants.append(path[: -len("/amp")])
    if path.endswith("/amp/"):
        variants.append(path[: -len("/amp/")])
    if "/amp/" in path:
        variants.append(path.replace("/amp/", "/", 1))
    params = parse_qs(parsed.query)
    if "amp" in params:
        params.pop("amp", None)
        variants.append(urlunparse(parsed._replace(query=urlencode(params, doseq=True))))
    return [urlunparse(parsed._replace(path=v)) for v in variants]


def _mobile_variants(url: str) -> list[str]:
    parsed = urlparse(url)
    netloc = parsed.netloc
    variants = []
    for prefix in ["m.", "mobile."]:
        if netloc.startswith(prefix):
            variants.append(urlunparse(parsed._replace(netloc=netloc[len(prefix) :])))
    return variants


def _extract_wrapped_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "news.google.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        for key in ["url", "q", "u"]:
            if key in params:
                return params[key][0]
    if "feedproxy.google.com" in parsed.netloc:
        return None
    return None


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>]+", text or "")


def _build_search_queries(meta: dict) -> list[str]:
    title = meta.get("title") or ""
    publisher = meta.get("publisher") or ""
    original_url = meta.get("original_url") or ""
    domain = urlparse(original_url).netloc if original_url else ""
    queries = []
    if publisher and title:
        queries.append(f"{publisher} {title}")
    if title:
        queries.append(title)
    if domain and title:
        queries.append(f"site:{domain} {title}")
    return queries


@dataclass
class PrimarySourceResolution:
    resolved_url: str | None
    report: dict
    selected_validation: UrlValidationResult | None


class PrimarySourceResolver:
    def __init__(self, api_keys: dict | None = None):
        self.config = api_keys or load_config()

    def resolve(self, primary: dict, article: dict | None = None) -> PrimarySourceResolution:
        report = {"candidates_tried": [], "selected": None, "reason": None}
        candidates = []
        primary_obj = (primary or {}).get("primary_source") or {}
        if primary_obj.get("url"):
            candidates.append(primary_obj.get("url"))
        for alt in primary.get("alternatives") or []:
            if isinstance(alt, dict) and alt.get("url"):
                candidates.append(alt.get("url"))

        meta = {
            "title": primary_obj.get("title") or "",
            "publisher": primary_obj.get("publisher_guess") or "",
            "original_url": (article or {}).get("source_url") or "",
            "type_guess": primary_obj.get("type_guess") or "",
        }

        for candidate in candidates:
            resolved = self._resolve_candidate(candidate, meta, report, primary)
            if resolved and resolved.ok:
                report["selected"] = resolved.final_url
                report["reason"] = "validated_candidate"
                report["source_type"] = "primary"
                article_ref = _extract_article_ref(article)
                update_registry(
                    resolved.final_url or candidate,
                    "primary",
                    article_ref.get("id"),
                    filename=article_ref.get("filename"),
                    run_id=article_ref.get("run_id"),
                    date=article_ref.get("date"),
                )
                return PrimarySourceResolution(resolved.final_url, report, resolved)

        rediscovered = self._rediscover(meta, report)
        if rediscovered:
            report["selected"] = rediscovered.final_url
            report["reason"] = "rediscovered"
            report["source_type"] = "primary"
            article_ref = _extract_article_ref(article)
            update_registry(
                rediscovered.final_url or "",
                "primary",
                article_ref.get("id"),
                filename=article_ref.get("filename"),
                run_id=article_ref.get("run_id"),
                date=article_ref.get("date"),
            )
            return PrimarySourceResolution(rediscovered.final_url, report, rediscovered)

        fallback_url = (article or {}).get("source_url") or None
        if fallback_url:
            report["selected"] = fallback_url
            report["reason"] = "fallback_to_news"
            report["source_type"] = "news"
            if primary is not None:
                primary.setdefault("primary_source", {})
                primary["primary_source"]["source_type"] = "news"
            article_ref = _extract_article_ref(article)
            update_registry(
                fallback_url,
                "news",
                article_ref.get("id"),
                filename=article_ref.get("filename"),
                run_id=article_ref.get("run_id"),
                date=article_ref.get("date"),
            )
            return PrimarySourceResolution(fallback_url, report, None)

        report["reason"] = "no_valid_primary_source"
        report["source_type"] = "news"
        return PrimarySourceResolution(None, report, None)

    def _resolve_candidate(
        self,
        candidate_url: str,
        meta: dict,
        report: dict,
        primary: dict | None,
    ) -> UrlValidationResult | None:
        normalized = _normalize_url(candidate_url)
        expected_pdf = normalized.lower().endswith(".pdf") or "pdf" in meta.get("type_guess", "").lower()
        validation = _validate_url(normalized, expected_pdf=expected_pdf)
        report["candidates_tried"].append(vars(validation))
        if validation.ok:
            if primary is not None:
                primary.setdefault("primary_source", {})
                primary["primary_source"]["source_type"] = "primary"
            return validation

        wrapped = _extract_wrapped_url(normalized)
        if wrapped:
            wrapped_norm = _normalize_url(wrapped)
            wrapped_val = _validate_url(wrapped_norm, expected_pdf=expected_pdf)
            report["candidates_tried"].append(vars(wrapped_val))
            if wrapped_val.ok:
                return wrapped_val

        for variant in _amp_variants(normalized) + _mobile_variants(normalized):
            variant_norm = _normalize_url(variant)
            variant_val = _validate_url(variant_norm, expected_pdf=expected_pdf)
            report["candidates_tried"].append(vars(variant_val))
            if variant_val.ok:
                return variant_val
        return None

    def _rediscover(self, meta: dict, report: dict) -> UrlValidationResult | None:
        api_key = self.config.get("GEMINI_API_KEY")
        if not api_key:
            return None
        queries = _build_search_queries(meta)
        if not queries:
            return None
        client = GeminiSearchClient(api_key=api_key)
        for query in queries:
            try:
                result = client.generate(
                    "Find the official primary source URL for the referenced document or announcement.",
                    query,
                )
            except LLMError:
                continue
            urls = _extract_urls(result)
            for url in urls[:5]:
                normalized = _normalize_url(url)
                expected_pdf = normalized.lower().endswith(".pdf")
                validation = _validate_url(normalized, expected_pdf=expected_pdf)
                report["candidates_tried"].append(vars(validation))
                if validation.ok:
                    return validation
        return None


def _extract_article_ref(article: dict | None) -> dict:
    if not article:
        return {}
    ref = {}
    for key in ("article_id", "id", "file_id", "profile_name"):
        value = article.get(key)
        if value:
            ref["id"] = str(value)
            break
    for key in ("filename", "_filename", "file_name"):
        value = article.get(key)
        if value:
            ref["filename"] = value
            break
    for key in ("run_id", "agent_run_id", "_run_id"):
        value = article.get(key)
        if value:
            ref["run_id"] = str(value)
            break
    for key in ("date_time", "date"):
        value = article.get(key)
        if value:
            ref["date"] = value
            break
    return ref


def _extract_article_id(article: dict | None) -> str | None:
    if not article:
        return None
    for key in ("article_id", "id", "file_id", "profile_name"):
        value = article.get(key)
        if value:
            return str(value)
    return None

ERROR_SIGNATURES = [
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
    "content not available",
    "article removed",
    "unpublished",
    "no longer available",
    "access denied",
]

HOMEPAGE_INDICATORS = [
    "/index",
    "/home",
    "/about",
    "/qui-som",
    "/nosotros",
    "/associacio",
    "/asociacion",
    "/contact",
    "/contacte",
]


def _validate_url(url: str, expected_pdf: bool = False, timeout: int = 20) -> UrlValidationResult:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers=headers)
    except requests.RequestException:
        response = None

    if response is None or response.status_code >= 400 or response.status_code == 0:
        try:
            response = requests.get(url, allow_redirects=True, timeout=timeout, headers=headers)
        except requests.RequestException as exc:
            return UrlValidationResult(
                original_url=url,
                final_url=None,
                status_code=None,
                content_type=None,
                content_length=None,
                redirect_chain=[],
                ok=False,
                reason=f"request_error: {exc}",
            )

    redirect_chain = [resp.url for resp in response.history] if response.history else []
    status = response.status_code
    content_type = response.headers.get("Content-Type", "")
    length = len(response.content or b"")
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
    if "text/html" not in content_type.lower() and "pdf" not in content_type.lower():
        return UrlValidationResult(
            original_url=url,
            final_url=response.url,
            status_code=status,
            content_type=content_type,
            content_length=length,
            redirect_chain=redirect_chain,
            ok=False,
            reason="unsupported_content_type",
        )
    if expected_pdf and "pdf" not in content_type.lower():
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
    
    # Check for homepage/generic page paths
    parsed_path = urlparse(response.url).path.lower().rstrip('/')
    for indicator in HOMEPAGE_INDICATORS:
        if parsed_path == indicator or parsed_path.endswith(indicator):
            return UrlValidationResult(
                original_url=url,
                final_url=response.url,
                status_code=status,
                content_type=content_type,
                content_length=length,
                redirect_chain=redirect_chain,
                ok=False,
                reason="homepage_or_generic_page",
            )
    if "text/html" in content_type.lower():
        sample = (response.text or "")[:2000].lower()
        if any(token in sample for token in ERROR_SIGNATURES):
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
        if length < 400 and any(token in (response.text or "").lower() for token in ERROR_SIGNATURES):
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
