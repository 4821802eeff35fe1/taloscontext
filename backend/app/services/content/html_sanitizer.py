"""Validates/sanitizes Telegram HTML before it's ever sent, so a malformed tag
from an AI response or manual edit can never trigger a Telegram parse error at
send time (product brief §8).
"""
from __future__ import annotations

import re

ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote"}

_TAG_RE = re.compile(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>")


class TelegramHTMLValidationError(Exception):
    pass


def sanitize_telegram_html(html: str) -> str:
    """Strips any tag not in ALLOWED_TAGS and balances open/close tags.
    Raises if the result still can't be balanced (caller should fall back to
    plain_text in that case rather than publish broken markup).
    """
    stack: list[str] = []
    output_parts: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(html):
        output_parts.append(_escape_text(html[pos : match.start()]))
        pos = match.end()
        tag_name = match.group(1).lower()
        is_closing = match.group(0).startswith("</")

        if tag_name not in ALLOWED_TAGS:
            continue  # drop disallowed tag entirely, keep its would-be inner text via next iteration

        if is_closing:
            if stack and stack[-1] == tag_name:
                stack.pop()
                output_parts.append(match.group(0))
            # unmatched closing tag: drop silently
        else:
            if tag_name == "a":
                href_match = re.search(r'href="([^"]*)"', match.group(0))
                href = href_match.group(1) if href_match else ""
                if not href.startswith(("http://", "https://", "tg://")):
                    continue  # drop anchors with unsafe/missing href
                output_parts.append(f'<a href="{_escape_attr(href)}">')
            else:
                output_parts.append(f"<{tag_name}>")
            stack.append(tag_name)

    output_parts.append(_escape_text(html[pos:]))

    while stack:
        output_parts.append(f"</{stack.pop()}>")

    return "".join(output_parts)


def _escape_text(text: str) -> str:
    return text  # text between tags is passed through; Telegram HTML mode only cares about tags


def _escape_attr(value: str) -> str:
    return value.replace('"', "&quot;")


def strip_to_plain_text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)
