"""Resolves an AI-returned `cta_key` to an actual contact string.

AI never invents usernames/URLs — it only picks a key from a known vocabulary
(hr, affiliate, ceo, website, email, none, ...). Precedence: channel override
-> workspace default -> none.
"""
from __future__ import annotations

import json

KNOWN_CTA_KEYS = {"hr", "affiliate", "ceo", "website", "email", "none"}


class CTAResolverService:
    def resolve(
        self,
        *,
        cta_key: str | None,
        channel_cta_overrides_json: str,
        workspace_cta_defaults: dict[str, str],
    ) -> str | None:
        if not cta_key or cta_key == "none":
            return None

        channel_overrides: dict[str, str] = {}
        try:
            channel_overrides = json.loads(channel_cta_overrides_json or "{}")
        except (json.JSONDecodeError, TypeError):
            channel_overrides = {}

        if channel_overrides.get(cta_key):
            return channel_overrides[cta_key]
        if workspace_cta_defaults.get(cta_key):
            return workspace_cta_defaults[cta_key]
        return None
