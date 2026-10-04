import json

from app.services.content.cta_resolver import CTAResolverService


def test_resolves_none_key_to_none():
    service = CTAResolverService()
    assert service.resolve(cta_key=None, channel_cta_overrides_json="{}", workspace_cta_defaults={}) is None
    assert service.resolve(cta_key="none", channel_cta_overrides_json="{}", workspace_cta_defaults={}) is None


def test_channel_override_takes_precedence_over_workspace_default():
    service = CTAResolverService()
    result = service.resolve(
        cta_key="hr",
        channel_cta_overrides_json=json.dumps({"hr": "@channel_hr_contact"}),
        workspace_cta_defaults={"hr": "@workspace_hr_contact"},
    )
    assert result == "@channel_hr_contact"


def test_falls_back_to_workspace_default_when_no_channel_override():
    service = CTAResolverService()
    result = service.resolve(
        cta_key="website", channel_cta_overrides_json="{}", workspace_cta_defaults={"website": "https://example.com"}
    )
    assert result == "https://example.com"


def test_returns_none_when_key_unknown_everywhere():
    service = CTAResolverService()
    result = service.resolve(cta_key="affiliate", channel_cta_overrides_json="{}", workspace_cta_defaults={})
    assert result is None
