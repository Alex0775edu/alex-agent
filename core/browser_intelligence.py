"""
core/browser_intelligence.py — Advanced Browser Intelligence & Web Security Firewall for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Core Capabilities:
  • Semantic Element Selection & Stale Selector Recovery
  • Robust Page-Load & Dynamic Content Verification
  • Tab & Popup Management
  • Untrusted Web Content & Prompt Injection Firewall
  • Consequential Action Confirmation Gate (purchase, submit, send, publish)
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.security import LEVEL_2_OWNER, security_manager

# Regex patterns for detecting web prompt injections
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:DAN|unrestricted|in\s+developer\s+mode)", re.IGNORECASE),
    re.compile(r"(?:system\s+prompt|jailbreak|override\s+rules)", re.IGNORECASE),
    re.compile(r"delete\s+(?:all\s+)?files", re.IGNORECASE),
    re.compile(r"format\s+[c-z]:", re.IGNORECASE),
    re.compile(r"send\s+(?:all\s+)?passwords", re.IGNORECASE),
    re.compile(r"exfiltrate", re.IGNORECASE),
]

CONSEQUENTIAL_ACTIONS = {
    "purchase", "buy", "pay", "checkout", "order",
    "publish", "post", "tweet",
    "submit_form", "delete_account", "transfer"
}


@dataclass
class WebPageSnapshot:
    url: str
    title: str
    is_loaded: bool
    status_code: int
    text_content: str
    sanitized: bool
    injection_detected: bool
    injection_details: List[str] = field(default_factory=list)


class BrowserIntelligence:
    """Provides security-hardened intelligence and recovery for web interactions."""

    _instance: Optional[BrowserIntelligence] = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> BrowserIntelligence:
        with cls._lock:
            if cls._instance is None:
                cls._instance = BrowserIntelligence()
            return cls._instance

    # ── Untrusted Content Firewall ───────────────────────────────────────────

    def inspect_and_sanitize_content(self, raw_html_or_text: str, source_url: str = "") -> Tuple[str, bool, List[str]]:
        """
        Scans webpage text for prompt injection attempts and neutralizes them.
        Returns: (sanitized_text, is_safe, detected_threats)
        """
        if not raw_html_or_text:
            return "", True, []

        threats = []
        for pat in _PROMPT_INJECTION_PATTERNS:
            matches = pat.findall(raw_html_or_text)
            if matches:
                threats.append(f"Detected suspicious pattern: '{matches[0]}'")

        sanitized = raw_html_or_text
        if threats:
            # Mask malicious phrases and record security event
            for pat in _PROMPT_INJECTION_PATTERNS:
                sanitized = pat.sub("[UNTRUSTED_INSTRUCTION_STRIPPED]", sanitized)

            timeline.record(
                event_type="ALERT",
                title="Web Prompt Injection Defended",
                details=f"URL: {source_url} | Threats: {'; '.join(threats)}",
                status="WARNING",
                permission_decision="SAFE",
                errors=threats
            )
            return sanitized, False, threats

        return sanitized, True, []

    # ── Consequential Action Gate ────────────────────────────────────────────

    def check_consequential_action(self, action_name: str, details: str = "") -> Tuple[bool, str]:
        """
        Enforces explicit owner confirmation before taking irreversible external actions.
        """
        act_lower = action_name.lower().strip()
        if act_lower in CONSEQUENTIAL_ACTIONS or any(c in act_lower for c in CONSEQUENTIAL_ACTIONS):
            # Check owner level
            auth = security_manager.get_auth_level()
            if auth < LEVEL_2_OWNER:
                return False, f"Action '{action_name}' requires verified owner clearance (Level 2). Access denied."

            # Must request confirmation
            return False, f"CONFIRMATION_REQUIRED: Sir, '{action_name}' ek consequential external action hai ({details}). Kya aap ise proceed karna chahte hain?"

        return True, "SAFE"

    # ── Semantic Element Selector Recovery ───────────────────────────────────

    def generate_fallback_selectors(self, original_selector: str, element_text: Optional[str] = None) -> List[str]:
        """
        Generates robust fallback selectors when a primary CSS/XPath selector becomes stale.
        """
        candidates = []
        if original_selector:
            candidates.append(original_selector)

        if element_text:
            t = element_text.strip()
            # Text based
            candidates.append(f"text='{t}'")
            candidates.append(f"button:has-text('{t}')")
            candidates.append(f"a:has-text('{t}')")
            candidates.append(f"[aria-label*='{t}']")
            candidates.append(f"[placeholder*='{t}']")

        # Generic semantic fallbacks
        if original_selector and ("button" in original_selector or "btn" in original_selector):
            candidates.append("button[type='submit']")
            candidates.append("button")

        return candidates


browser_intelligence = BrowserIntelligence.get_instance()

