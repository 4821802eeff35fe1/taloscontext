"""Structured JSON logging with secret redaction.

Any field whose key matches REDACTED_KEYS is replaced before the event is
emitted — this is a deliberate second line of defense in addition to never
passing secrets into log calls in the first place.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

REDACTED_KEYS = {
    "password",
    "code",
    "session",
    "session_string",
    "token",
    "api_key",
    "secret",
    "authorization",
    "two_fa_password",
    "verification_code",
}


def _redact_processor(_logger: Any, _method_name: str, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging(json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
