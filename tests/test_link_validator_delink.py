from link_validator import validate_and_delink_outbound_links


def test_validate_and_delink_outbound_links_removes_link(monkeypatch):
    def fake_validate(url: str):
        return False, "status_404"

    monkeypatch.setattr("link_validator._validate_url_with_reason", fake_validate)
    content = '<p>See <a href="https://example.com/bad">example</a> now.</p>'
    updated, report = validate_and_delink_outbound_links(content, enabled=True)
    assert "<a" not in updated
    assert "example" in updated
    assert report["enabled"] is True
    assert report["checked"] == 1
    assert report["broken"] == 1
    assert report["removed_links"][0]["url"] == "https://example.com/bad"


def test_validate_and_delink_outbound_links_disabled():
    content = '<p>See <a href="https://example.com/bad">example</a> now.</p>'
    updated, report = validate_and_delink_outbound_links(content, enabled=False)
    assert updated == content
    assert report["enabled"] is False


def test_validate_and_delink_allows_only_whitelist():
    content = (
        '<p><a href="https://barna.news/story">internal</a> '
        '<a href="https://example.com/keep">keep</a> '
        '<a href="https://example.com/drop">drop</a></p>'
    )
    updated, report = validate_and_delink_outbound_links(
        content,
        enabled=True,
        allowed_urls={"https://example.com/keep"},
    )
    assert "https://example.com/keep" in updated
    assert "https://example.com/drop" not in updated
