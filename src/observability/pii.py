"""
PII scrubbing filter for log records.

Automatically redacts passwords, tokens, API keys, email addresses, and
other sensitive data before log lines are emitted.  Installed as a
``logging.Filter`` on every handler created by the structured logger.
"""

import logging
import re
from typing import FrozenSet, Pattern

# Patterns that match sensitive values in log messages.
_SENSITIVE_PATTERNS: list[tuple[Pattern, str]] = [
    # Bearer tokens / Authorization headers
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1[REDACTED]"),
    # Generic API keys / tokens in key=value or key:value
    (
        re.compile(
            r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|session_token|"
            r"cookie|access_token|refresh_token|private_key)"
            r"(\s*[:=]\s*)"
            r"(['\"]?)([^\s'\"]{4,})\3"
        ),
        r"\1\2\3[REDACTED]\3",
    ),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL_REDACTED]"),
    # Credit card–like 16-digit numbers
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD_REDACTED]"),
    # SSN-like patterns (US)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
]

# Record attribute names that should *always* be fully redacted when present.
_REDACT_ATTRS: FrozenSet[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "private_key",
        "session_token",
        "access_token",
        "refresh_token",
    }
)


class PiiScrubber(logging.Filter):
    """Logging filter that scrubs PII/secrets from log records.

    Attach to a handler or logger::

        logger.addFilter(PiiScrubber())
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 — stdlib name
        # Scrub the formatted message
        msg = record.getMessage()
        record.msg = _scrub_text(msg)
        record.args = None  # prevent double-formatting

        # Scrub well-known extra attributes
        for attr in _REDACT_ATTRS:
            if hasattr(record, attr):
                setattr(record, attr, "[REDACTED]")

        return True


def _scrub_text(text: str) -> str:
    """Apply all sensitive-data patterns to *text* and return the result."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
