"""Structured logging with credential redaction.

Every log record passes through a redaction filter so that secrets that leak
into messages, arguments or exception text are masked before they are written.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# Patterns that must never reach a log sink.
_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization|api[-_]?key|apikey|access[-_]?token|refresh[-_]?token|"
               r"client[-_]?secret|password|passwd|secret|bearer)\s*[:=]\s*([^\s,;\"'}]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(https?://[^:/\s]+):([^@/\s]+)@"),  # basic-auth in URL
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)

_REDACTED = "***REDACTED***"


def redact_text(value: str) -> str:
    for pattern in _REDACT_PATTERNS:
        if pattern.groups >= 2:
            value = pattern.sub(lambda m: f"{m.group(1)}={_REDACTED}", value)
        else:
            value = pattern.sub(_REDACTED, value)
    return value


_SENSITIVE_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token", "client_secret",
    "api_key", "apikey", "authorization", "private_key", "credential", "credentials",
    "encrypted_payload", "webhook_secret", "signing_secret",
}


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(key, v) for v in value)
    return value


def _redaction_processor(_logger: Any, _method: str, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        event_dict[key] = _redact_value(key, event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redaction_processor,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
