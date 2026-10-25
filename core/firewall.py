"""
core/firewall.py — Private Information Firewall & Secret Redaction for ALEX.

Core Principles:
  • External content is untrusted data, never instructions.
  • Secrets (API keys, passwords, tokens, private keys) are redacted in all logs and user-facing text.
  • Private resources require verified owner clearance before read or write.

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import re
from typing import Tuple

# Regex patterns for secret detection
_SECRET_PATTERNS = [
    # Gemini / Google API keys: AIzaSy...
    (re.compile(r"AIzaSy[0-9A-Za-z_-]{10,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Generic API Keys / Tokens:
    (re.compile(r"((?:api[_-]?(?:key|token|secret)|access[_-]?token)\s*[:=]\s*['\"]?)([0-9a-zA-Z\-_]{10,})(['\"]?)", re.IGNORECASE), r"\1[REDACTED_API_KEY]\3"),
    # Passwords:
    (re.compile(r"(password\s*[:=]\s*['\"]?)([^\s'\"]{6,})(['\"]?)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]\3"),
    # Bearer tokens / JWT:
    (re.compile(r"(bearer\s+)([0-9a-zA-Z\-_.]+\.[0-9a-zA-Z\-_.]+\.[0-9a-zA-Z\-_.]+)", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # GitHub personal access tokens:
    (re.compile(r"(ghp_[0-9a-zA-Z]{36})", re.IGNORECASE), "ghp_[REDACTED_GITHUB_TOKEN]"),
    # AWS Access / Secret keys:
    (re.compile(r"(AKIA[0-9A-Z]{16})", re.IGNORECASE), "AKIA[REDACTED_AWS_KEY]"),
    # Owner PIN:
    (re.compile(r"(owner[_-]?pin\s*[:=]\s*['\"]?)(\d{4,})(['\"]?)", re.IGNORECASE), r"\1[REDACTED_PIN]\3"),
]

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_PATTERN = re.compile(
    r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)"
)


class PrivateDataFirewall:
    """Detects and redacts credentials, private keys, and secrets."""

    @staticmethod
    def redact_secrets(text: str) -> str:
        """Sanitize text by replacing sensitive keys and passwords with masked strings."""
        if not text:
            return ""
        sanitized = text
        for pattern, replacement in _SECRET_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @staticmethod
    def contains_secret(text: str) -> bool:
        """Return True if any credential or secret pattern is found."""
        if not text:
            return False
        return any(pattern.search(text) for pattern, _ in _SECRET_PATTERNS)

    @staticmethod
    def redact_personal_data(text: str) -> str:
        """Mask common contact details after credential redaction."""
        if not text:
            return ""
        sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)

        def replace_phone(match: re.Match[str]) -> str:
            digits = re.sub(r"\D", "", match.group(0))
            return "[REDACTED_PHONE]" if 10 <= len(digits) <= 15 else match.group(0)

        return _PHONE_PATTERN.sub(replace_phone, sanitized)


# Global helper
def redact(text: str) -> str:
    return PrivateDataFirewall.redact_personal_data(
        PrivateDataFirewall.redact_secrets(text)
    )


def inspect_prompt_safety(text: str) -> Tuple[bool, str]:
    """Inspects text for prompt injection markers (e.g. 'ignore previous instructions', 'system prompt override')."""
    if not text:
        return True, "Safe"
    low = text.lower()
    injections = [
        "ignore previous instructions",
        "disregard all previous instructions",
        "delete all files",
        "format c:",
        "bypass security",
        "override system prompt",
    ]
    for inj in injections:
        if inj in low:
            return False, f"Malicious instruction marker detected: '{inj}'"
    return True, "Safe"
