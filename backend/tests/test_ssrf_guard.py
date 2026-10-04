import pytest

from app.services.security.ssrf_guard import SSRFBlockedError, assert_url_is_safe


def test_rejects_private_ip_literal():
    with pytest.raises(SSRFBlockedError):
        assert_url_is_safe("http://127.0.0.1/admin")


def test_rejects_link_local_metadata_ip():
    with pytest.raises(SSRFBlockedError):
        assert_url_is_safe("http://169.254.169.254/latest/meta-data/")


def test_rejects_non_http_scheme():
    with pytest.raises(SSRFBlockedError):
        assert_url_is_safe("file:///etc/passwd")


def test_allows_public_https_url():
    assert_url_is_safe("https://example.com/article")
