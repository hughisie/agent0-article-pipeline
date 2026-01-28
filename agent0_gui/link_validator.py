from url_validator import validate_url


def validate_primary_source(url: str) -> dict:
    result = validate_url(url)
    return {
        "ok": result.ok,
        "final_url": result.final_url,
        "reason": result.reason,
        "status_code": result.status_code,
    }
