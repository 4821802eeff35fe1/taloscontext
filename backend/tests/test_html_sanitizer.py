from app.services.content.html_sanitizer import sanitize_telegram_html


def test_allowed_tags_pass_through():
    html = "<b>Bold</b> and <i>italic</i> text"
    assert sanitize_telegram_html(html) == html


def test_disallowed_tags_are_stripped():
    html = "<div><b>Bold</b></div><script>alert(1)</script>"
    result = sanitize_telegram_html(html)
    assert "<div>" not in result
    assert "<script>" not in result
    assert "<b>Bold</b>" in result


def test_unclosed_tag_is_auto_closed():
    html = "<b>Unclosed bold"
    result = sanitize_telegram_html(html)
    assert result == "<b>Unclosed bold</b>"


def test_anchor_without_safe_href_is_dropped():
    html = '<a href="javascript:alert(1)">click</a>'
    result = sanitize_telegram_html(html)
    assert "href" not in result


def test_anchor_with_safe_href_is_kept():
    html = '<a href="https://example.com">click</a>'
    result = sanitize_telegram_html(html)
    assert 'href="https://example.com"' in result
