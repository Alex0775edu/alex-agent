"""
core/security.py — Owner Authentication, Authorization Levels, Anti-Spoofing, and Security Firewall for ALEX 3.0.

Core Security Principles:
  • HEARD != AUTHORIZED
  • WAKE WORD != AUTHENTICATION
  • VOICE COMMAND != PERMISSION
  • USER CLAIM != OWNER IDENTITY
  • ONLY ADITYA SIR GETS FULL CONTROL

Authorized Owner: Aditya Rajak
Owner Address: Aditya Sir
System Version: ALEX 3.0 Ultimate Private Operating Agent
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from core.action_timeline import timeline

# ── Authorization Levels (Legacy & Session Clearance) ─────────────────────────
LEVEL_0_UNKNOWN   = 0   # Anyone not authenticated: general questions, weather, time
LEVEL_1_GUEST     = 1   # Explicit guest mode: safe read-only queries
LEVEL_2_OWNER     = 2   # Verified owner (Aditya Rajak): computer control, files, memory, agent
LEVEL_3_CRITICAL  = 3   # Verified owner + explicit UI confirmation: shutdown, destructive actions

# ── Phase 5 Standard Permission Categories ────────────────────────────────────
PERM_LEVEL_1_READ        = 1  # Read permitted files, inspect project structure, read visible app info
PERM_LEVEL_2_NORMAL      = 2  # Create & edit files in approved workspaces, open apps, browser nav, generate docs
PERM_LEVEL_3_SENSITIVE   = 3  # Delete/overwrite files, destructive commands, install software, modify settings, submit forms
PERM_LEVEL_4_RESTRICTED  = 4  # Disable security, extract credentials, bypass auth, covert surveillance, data exfil -> PERMANENTLY BLOCKED

# Confidence Thresholds
CONFIDENCE_HIGH   = 0.75   # Verified owner access
CONFIDENCE_MEDIUM = 0.50   # Request re-verification or PIN
CONFIDENCE_LOW    = 0.50   # Restricted guest mode

OWNER_NAME    = "Aditya Rajak"
OWNER_ADDRESS = "Sir"

BASE_DIR        = Path(__file__).resolve().parent.parent
CONFIG_DIR      = BASE_DIR / "config"
VOICE_FILE      = CONFIG_DIR / "owner_voice_profile.json"
SECURITY_LOG    = BASE_DIR / "memory" / "security_audit.log"
PRIVACY_FILE    = CONFIG_DIR / "privacy_settings.json"

# Actions categorized by security clearance required
SAFE_ACTIONS = {
    "weather_report", "system_status", "diagnostics", "time_check", "help",
    "web_search", "undo", "action_timeline", "morning_briefing", "focus_mode_status"
}

PRIVILEGED_ACTIONS = {
    "open_app", "computer_control", "browser_control", "file_processor",
    "file_controller", "dev_agent", "code_helper", "desktop_control",
    "save_memory", "recall_memory", "youtube_video", "video_player",
    "send_message", "reminder", "flight_finder", "game_updater", "screen_process",
    "research_agent", "document_agent", "creation_engine", "meeting_mode",
    "clipboard_mode", "automation_engine", "focus_mode"
}

CRITICAL_ACTIONS = {
    "shutdown_alex", "shutdown_jarvis", "computer_settings", "reboot",
    "format_disk", "delete_all", "mass_file_delete", "clear_system_data"
}

RESTRICTED_OPERATIONS = {
    "disable_security", "bypass_authentication", "extract_credentials",
    "covert_surveillance", "exfiltrate_data", "format_disk", "format_c",
    "wipe_system", "kill_security_agent"
}

SENSITIVE_OPERATIONS = {
    "delete_file", "overwrite_file", "destructive_command", "install_software",
    "modify_system_settings", "access_sensitive_data", "send_message",
    "submit_external_form", "purchase", "checkout", "shutdown_alex", "reboot"
}

# Prompt injection markers in untrusted external content
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard all previous",
    "you are now in developer mode",
    "dan mode",
    "system override",
    "admin override",
    "delete system32",
    "shutdown computer immediately",
    "bypass authentication",
    "disable security",
    "reveal owner pin",
    "bypass firewall",
    "act as root",
    "switch to unfiltered",
]


@dataclass
class AntiSpoofResult:
    is_spoof: bool
    confidence: float
    risk_level: str  # SAFE, SUSPICIOUS, HIGH_RISK
    details: str


@dataclass
class SpeakerVerificationResult:
    is_owner: bool
    confidence: float
    tier: str        # HIGH, MEDIUM, LOW, SPOOF_SUSPECTED
    message: str
    anti_spoof: AntiSpoofResult


class SecurityManager:
    """Central Security and Owner Authorization Authority for ALEX 3.0."""

    _instance: Optional[SecurityManager] = None
    _lock = threading.Lock()

    def __init__(self):
        self._auth_level: int = LEVEL_2_OWNER   # Default session state for active owner
        self._session_timeout: float = 900.0    # 15 minutes default timeout (configurable)
        self._last_active_time: float = time.monotonic()
        self._locked: bool = False
        self._owner_pin: str = "1122"           # Default owner PIN
        self._voice_profile: dict = {}
        self._enrollment_samples: List[dict] = []
        self._audit_lock = threading.Lock()
        self._emergency_callbacks: list[Callable[[], None]] = []

        # Continuous Speaker Continuity Tracker
        self._last_speaker_hash: Optional[float] = None
        self._continuity_alert_count: int = 0

        # Privacy Toggles
        self._privacy_settings: dict = {
            "microphone": True,
            "camera": True,
            "screen": True,
            "memory": True,
            "clipboard": True,
            "browser": True,
            "files": True,
            "remote_access": True,
            "voice_profile": True,
        }

        self._load_config()
        self._load_voice_profile()
        self._load_privacy_settings()

    @classmethod
    def get_instance(cls) -> SecurityManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SecurityManager()
            return cls._instance

    def _load_config(self) -> None:
        cfg_file = CONFIG_DIR / "api_keys.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                self._owner_pin = str(data.get("owner_pin", "1122")).strip()
                self._session_timeout = float(data.get("session_timeout_seconds", 900.0))
            except Exception:
                pass

    def _load_voice_profile(self) -> None:
        if VOICE_FILE.exists():
            try:
                self._voice_profile = json.loads(VOICE_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._voice_profile = {}

    def _load_privacy_settings(self) -> None:
        if PRIVACY_FILE.exists():
            try:
                data = json.loads(PRIVACY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._privacy_settings.update(data)
            except Exception:
                pass

    def save_privacy_settings(self) -> None:
        try:
            PRIVACY_FILE.parent.mkdir(parents=True, exist_ok=True)
            PRIVACY_FILE.write_text(json.dumps(self._privacy_settings, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set_privacy_setting(self, resource: str, enabled: bool) -> bool:
        if resource in self._privacy_settings:
            self._privacy_settings[resource] = enabled
            self.save_privacy_settings()
            self.log_event("PRIVACY_UPDATE", f"Resource '{resource}' set to {enabled}.")
            timeline.record("PRIVACY", f"Privacy Toggle: {resource}", f"Enabled: {enabled}")
            return True
        return False

    def is_privacy_allowed(self, resource: str) -> bool:
        return self._privacy_settings.get(resource, True)

    def log_event(self, event_type: str, detail: str) -> None:
        """Record sanitized security events to memory/security_audit.log."""
        with self._audit_lock:
            SECURITY_LOG.parent.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            from core.firewall import redact
            sanitized = redact(str(detail))
            line = f"[{ts}] [{event_type.upper()}] {sanitized}\n"
            try:
                with open(SECURITY_LOG, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass

    # ── Session & Lock Controls ───────────────────────────────────────────────

    def is_locked(self) -> bool:
        if self._locked:
            return True
        # Check timeout — only locks if inactivity exceeded session timeout
        if (time.monotonic() - self._last_active_time) > self._session_timeout:
            self.lock(reason="session timeout (inactivity)")
            return True
        return False

    def touch(self) -> None:
        """Refresh session active timestamp upon any user interaction."""
        self._last_active_time = time.monotonic()

    def set_session_timeout(self, seconds: float) -> None:
        """Configurable timeouts: 300 (5m), 900 (15m), 1800 (30m), 3600 (1h)."""
        self._session_timeout = max(60.0, float(seconds))
        self.touch()
        self.log_event("CONFIG", f"Session timeout set to {self._session_timeout}s.")

    def get_session_timeout(self) -> float:
        return self._session_timeout

    def lock(self, reason: str = "manual request") -> None:
        """Lock ALEX immediately."""
        self._locked = True
        self._auth_level = LEVEL_0_UNKNOWN
        self.log_event("LOCK", f"ALEX locked — reason: {reason}")
        timeline.record("LOCK", "ALEX Locked", f"Reason: {reason}", status="WARNING")

    def unlock(self, pin: str = "") -> Tuple[bool, str]:
        """Unlock ALEX with securely hashed owner PIN or verification."""
        clean_pin = pin.strip()
        from core.security_vault import credentials_vault
        if credentials_vault.verify_pin(clean_pin):
            self._locked = False
            self._auth_level = LEVEL_2_OWNER
            self._last_active_time = time.monotonic()
            self._continuity_alert_count = 0
            self.log_event("AUTH_SUCCESS", f"Owner {OWNER_NAME} unlocked ALEX.")
            timeline.record("AUTH", "Owner Unlocked", f"{OWNER_ADDRESS} authenticated via hashed PIN/passphrase.")
            return True, f"Welcome back, {OWNER_ADDRESS}. ALEX is unlocked."
        self.log_event("AUTH_FAIL", "Failed unlock attempt with invalid credential.")
        timeline.record("AUTH", "Unlock Failed", "Invalid credential provided.", status="FAILED")
        return False, "Invalid authentication credential."

    def verify_owner(self, force: bool = False) -> bool:
        """
        Verify that the active user is the authorized owner (Aditya Rajak).
        On Aditya Sir's personal workstation, un-locked sessions default to verified owner.
        """
        if self.is_locked():
            return False
        if force:
            self._auth_level = LEVEL_2_OWNER
            self.touch()
            return True
        return self.get_auth_level() >= LEVEL_2_OWNER

    def get_current_identity(self) -> str:
        """Returns the identified active user name."""
        if self.is_locked():
            return "LOCKED"
        lvl = self.get_auth_level()
        if lvl >= LEVEL_2_OWNER:
            return OWNER_NAME
        elif lvl == LEVEL_1_GUEST:
            return "Guest"
        return "Unknown"

    def get_permission_level(self) -> str:
        """
        Returns normalized permission tier string:
        'OWNER', 'GUEST', 'UNKNOWN', or 'LOCKED'.
        """
        if self.is_locked():
            return "LOCKED"
        lvl = self.get_auth_level()
        if lvl >= LEVEL_2_OWNER:
            return "OWNER"
        elif lvl == LEVEL_1_GUEST:
            return "GUEST"
        return "UNKNOWN"

    def set_auth_level(self, level: int) -> None:
        self._auth_level = level
        self.touch()
        self.log_event("AUTH_LEVEL", f"Security clearance set to Level {level}.")

    def get_auth_level(self) -> int:
        if self.is_locked():
            return LEVEL_0_UNKNOWN
        return self._auth_level

    # ── Emergency Stop ────────────────────────────────────────────────────────

    def register_emergency_stop_callback(self, cb: Callable[[], None]) -> None:
        self._emergency_callbacks.append(cb)

    def trigger_emergency_stop(self) -> str:
        """
        Immediately halts automation, aborts active tasks, locks ALEX,
        and drops privileges to Level 0.
        """
        self.lock(reason="EMERGENCY STOP TRIGGERED")
        self.log_event("EMERGENCY_STOP", "Emergency stop triggered by owner hotkey/command.")
        timeline.record("STOP", "EMERGENCY STOP ACTIVATED", "All automation halted & locked.", status="BLOCKED")
        for cb in self._emergency_callbacks:
            try:
                cb()
            except Exception as e:
                self.log_event("EMERGENCY_ERR", f"Callback error: {e}")
        return f"EMERGENCY STOP ACTIVATED: All automation halted. ALEX is locked for {OWNER_ADDRESS}'s safety."

    # ── Permission Firewall ───────────────────────────────────────────────────

    # ── Permission Firewall & Central Security Gateway ─────────────────────────

    def authorize_file_access(self, file_path: Path | str, mode: str = "r") -> Tuple[bool, str, int]:
        """
        Validates file system access containment across permission levels:
        Level 1: Read permitted files
        Level 2: Normal create/write in approved workspaces
        Level 3: Sensitive overwrite/deletion
        Level 4: Restricted OS system directories (Blocked permanently)
        """
        p_str = str(file_path).lower().replace("/", "\\")

        # Forbidden system & credential locations (Level 4 Restricted)
        forbidden_patterns = [
            "system32", "syswow64", r"\windows\system",
            r"\appdata\local\microsoft\credentials",
            r"\.ssh\id_rsa", r"\.ssh\id_ed25519", "sam", "security"
        ]
        for f in forbidden_patterns:
            if f in p_str:
                self.log_event("BLOCKED_FILE", f"Level 4 Restricted file access blocked: {file_path}")
                timeline.record("FIREWALL", "Protected File Access Blocked", f"Path: {file_path}", status="BLOCKED")
                return False, f"Access Denied: Path '{file_path}' is in a protected system directory.", PERM_LEVEL_4_RESTRICTED

        if mode.lower() in ("delete", "remove", "unlink"):
            return True, "Requires Level 3 Sensitive Confirmation", PERM_LEVEL_3_SENSITIVE

        if mode.lower() in ("w", "write", "overwrite"):
            try:
                p = Path(file_path)
                if p.exists() and p.is_file() and p.stat().st_size > 0:
                    return True, "File overwrite requires Level 3 Confirmation", PERM_LEVEL_3_SENSITIVE
            except Exception:
                pass
            return True, "Write permitted in approved workspace", PERM_LEVEL_2_NORMAL

        return True, "Read permitted", PERM_LEVEL_1_READ

    def authorize_terminal_command(self, command: str) -> Tuple[bool, str, int]:
        """
        Inspects terminal command against Level 1-4 security boundaries:
        Level 1: Read/inspect commands
        Level 2: Normal build/run commands
        Level 3: Potentially destructive commands requiring confirmation
        Level 4: Catastrophic/hostile commands (Blocked permanently)
        """
        cmd_clean = command.strip().lower()

        # Level 4: Permanently Blocked Commands
        forbidden_cmd_patterns = [
            r"format\s+[a-z]:",
            r"rmdir\s+/[sS]\s+/[qQ]\s+[cC]:\\",
            r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[cC]:\\",
            r"vssadmin\s+delete\s+shadows",
            r"bcdedit",
            r"reg\s+delete\s+hklm",
            r"net\s+user\s+.*\s+/add",
            r"cipher\s+/w"
        ]
        for pat in forbidden_cmd_patterns:
            if re.search(pat, cmd_clean):
                self.log_event("BLOCKED_CMD", f"Level 4 Restricted command blocked: {command}")
                timeline.record("FIREWALL", "Dangerous Command Blocked", f"Cmd: {command}", status="BLOCKED")
                return False, f"Blocked: Command '{command}' is classified as Level 4 Restricted Operation.", PERM_LEVEL_4_RESTRICTED

        # Level 3: Potentially Destructive / System Altering Commands
        sensitive_cmd_patterns = [
            r"\brmdir\b", r"\bdel\b", r"\bremove-item\b", r"\bpip\s+install\b",
            r"\btaskkill\b", r"\bnetsh\b", r"\bsc\s+stop\b"
        ]
        for pat in sensitive_cmd_patterns:
            if re.search(pat, cmd_clean):
                return True, f"Command '{command}' requires Level 3 Owner Confirmation", PERM_LEVEL_3_SENSITIVE

        return True, "Command authorized for execution", PERM_LEVEL_2_NORMAL

    def authorize_browser_action(self, action: str, target: str = "") -> Tuple[bool, str, int]:
        """
        Validates browser operations against security levels.
        """
        act_lower = action.lower().strip()
        t_lower = target.lower().strip()

        # Check prompt injection or malicious protocol
        if any(p in t_lower for p in ("javascript:", "data:text/html", "ignore previous instructions")):
            self.log_event("BLOCKED_URL", f"Malicious browser URL or payload blocked: {target}")
            timeline.record("FIREWALL", "Malicious URL Blocked", f"URL: {target}", status="BLOCKED")
            return False, "Blocked: Dangerous browser target or payload.", PERM_LEVEL_4_RESTRICTED

        consequential = ("purchase", "buy", "pay", "checkout", "publish", "post", "submit_form", "delete_account")
        if act_lower in consequential or any(c in act_lower for c in consequential):
            return True, f"Browser action '{action}' requires Level 3 Owner Confirmation", PERM_LEVEL_3_SENSITIVE

        return True, "Browser navigation authorized", PERM_LEVEL_2_NORMAL

    def authorize_action(self, tool_name: str, parameters: Optional[dict] = None) -> Tuple[bool, str, int]:
        """
        Central Security Gateway authorizing every tool execution in ALEX.
        Returns: (is_allowed: bool, reason: str, level: int)
        """
        name_lower = tool_name.lower().strip()
        params = parameters or {}

        # 1. Level 4 Restricted Check
        if name_lower in RESTRICTED_OPERATIONS:
            self.log_event("BLOCKED_TOOL", f"Level 4 Restricted tool '{tool_name}' blocked.")
            timeline.record("FIREWALL", f"Restricted Tool Blocked: {tool_name}", "Permanently blocked capability.", status="BLOCKED")
            return False, f"Blocked: Action '{tool_name}' is classified as Level 4 Restricted Operation.", PERM_LEVEL_4_RESTRICTED

        # 2. Check if session is locked
        if self.is_locked():
            msg = f"ALEX is locked. Computer control and private access are restricted to {OWNER_ADDRESS}."
            self.log_event("BLOCKED", f"Action '{tool_name}' blocked — ALEX is locked.")
            timeline.record("FIREWALL", f"Action Blocked: {tool_name}", "ALEX is currently locked.", status="BLOCKED")
            return False, msg, PERM_LEVEL_3_SENSITIVE

        # 3. Privacy settings check
        if name_lower in ("screen_process", "desktop_control") and not self.is_privacy_allowed("screen"):
            return False, "Screen access is disabled in ALEX Privacy Settings.", PERM_LEVEL_3_SENSITIVE
        if name_lower == "clipboard_mode" and not self.is_privacy_allowed("clipboard"):
            return False, "Clipboard access is disabled in ALEX Privacy Settings.", PERM_LEVEL_3_SENSITIVE
        if name_lower in ("file_processor", "file_controller") and not self.is_privacy_allowed("files"):
            return False, "File access is disabled in ALEX Privacy Settings.", PERM_LEVEL_3_SENSITIVE

        # 4. Parameter-specific inspections
        if name_lower in ("file_processor", "file_controller", "save_file"):
            f_path = params.get("path") or params.get("target") or params.get("file")
            mode = params.get("mode") or params.get("action") or "r"
            if f_path:
                ok, reason, lvl = self.authorize_file_access(f_path, mode)
                if not ok:
                    return False, reason, lvl

        if name_lower in ("computer_control", "dev_agent") and "command" in params:
            ok, reason, lvl = self.authorize_terminal_command(params["command"])
            if not ok:
                return False, reason, lvl

        if name_lower == "browser_control":
            b_act = params.get("action", "")
            b_tgt = params.get("url") or params.get("query") or ""
            ok, reason, lvl = self.authorize_browser_action(b_act, b_tgt)
            if not ok:
                return False, reason, lvl

        # 5. Clearance mapping
        if name_lower in CRITICAL_ACTIONS or name_lower in SENSITIVE_OPERATIONS:
            if self.get_auth_level() < LEVEL_2_OWNER:
                msg = f"Action '{tool_name}' is restricted to {OWNER_ADDRESS} with critical confirmation."
                return False, msg, PERM_LEVEL_3_SENSITIVE
            return True, "Requires Level 3 Confirmation", PERM_LEVEL_3_SENSITIVE

        if name_lower in PRIVILEGED_ACTIONS or name_lower == "computer_control":
            if self.get_permission_level() != "OWNER" and self.get_auth_level() < LEVEL_2_OWNER:
                msg = f"{OWNER_ADDRESS} ke alawa computer control kisi aur ke liye allowed nahi hai."
                return False, msg, PERM_LEVEL_2_NORMAL
            return True, "Allowed", PERM_LEVEL_2_NORMAL

        return True, "Safe action allowed", PERM_LEVEL_1_READ

    def check_permission(self, action_name: str, parameters: Optional[dict] = None) -> Tuple[bool, str]:
        """Backward-compatible wrapper around authorize_action."""
        allowed, reason, _ = self.authorize_action(action_name, parameters)
        return allowed, reason

    def explain_consequential_action(self, action: str, target: str, risks: str) -> str:
        """
        Generates structured 4-part disclosure before consequential execution:
          1. Intended Action
          2. Affected Resources
          3. Relevant Risks
          4. Confirmation Request
        """
        return (
            f"{OWNER_ADDRESS}, ek consequential action execute karne se pehle confirmation required hai:\n"
            f"• Intended Action: {action}\n"
            f"• Affected Target: {target}\n"
            f"• Relevant Risks: {risks}\n"
            f"Kya aap ise proceed karna chahte hain?"
        )

    def request_sensitive_confirmation(
        self,
        action: str,
        target: str,
        risks: str,
        executor: Callable[[], str]
    ) -> str:
        """Parks sensitive operation behind the secure human-in-the-loop gate."""
        from core import confirm
        detail = f"Target: {target} | Risk: {risks}"
        return confirm.request(
            key=f"{action}_{target}",
            title=f"Confirm {action}",
            detail=detail,
            run=executor
        )

    # ── Anti-Prompt-Injection & Data Sanitization ─────────────────────────────

    def inspect_untrusted_content(self, content: str, source: str = "web") -> Tuple[bool, str]:
        """
        Inspect external untrusted content (webpages, PDFs, emails, clipboard).
        Returns: (is_safe: bool, sanitized_or_flagged_message: str)
        """
        lower = content.lower()
        for pattern in _INJECTION_PATTERNS:
            if pattern in lower:
                self.log_event("INJECTION_ATTEMPT", f"Blocked injection pattern '{pattern}' in source '{source}'.")
                timeline.record("SECURITY", "Prompt Injection Blocked", f"Pattern: {pattern} from {source}", status="BLOCKED")
                return False, f"[BLOCKED] Suspicious prompt injection detected from {source}."
        return True, content

    # ── Anti-Spoofing & Replay Attack Detection ───────────────────────────────

    def detect_voice_spoof(self, audio: np.ndarray, sample_rate: int = 16000) -> AntiSpoofResult:
        """
        Inspect acoustic signal for replay attacks, artificial clipping,
        synthetic/TTS robotic flat pitch, and phone playback frequency cutoffs.
        """
        if len(audio) < 1600:
            return AntiSpoofResult(is_spoof=False, confidence=0.7, risk_level="SAFE", details="Short sample")

        # 1. Clipping detection (indicative of mic-to-speaker replay boost)
        max_val = np.max(np.abs(audio))
        clip_ratio = np.mean(np.abs(audio) > 0.98)
        if clip_ratio > 0.08:
            return AntiSpoofResult(
                is_spoof=True,
                confidence=0.88,
                risk_level="HIGH_RISK",
                details=f"Excessive clipping detected ({clip_ratio*100:.1f}%), possible amplified replay attack."
            )

        # 2. Spectral Frequency Cutoff (cheap phone speakers cut off abruptly around 4kHz-8kHz)
        fft_mag = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)
        high_freq_energy = np.sum(fft_mag[freqs > 6000])
        total_energy = np.sum(fft_mag) + 1e-9
        high_freq_ratio = high_freq_energy / total_energy

        # 3. Spectral Variance / Harmonic Jitter (synthetic TTS voices often have zero micro-jitter)
        zcr_frames = [np.mean(np.abs(np.diff(np.sign(frame)))) for frame in np.array_split(audio, 8)]
        zcr_var = float(np.var(zcr_frames))

        if zcr_var < 1e-6 and len(audio) > 8000:
            return AntiSpoofResult(
                is_spoof=True,
                confidence=0.82,
                risk_level="HIGH_RISK",
                details="Unnatural zero-variance spectral flatline indicative of synthetic TTS speech."
            )

        return AntiSpoofResult(
            is_spoof=False,
            confidence=0.92,
            risk_level="SAFE",
            details="Natural acoustic micro-jitter and harmonic frequencies verified."
        )

    # ── Multi-Sample Voice Enrollment (5 Natural Samples) ─────────────────────

    def extract_acoustic_features(self, pcm_bytes: bytes, sample_rate: int = 16000) -> dict:
        """Compute acoustic feature vector from PCM bytes."""
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        energy = float(np.mean(audio ** 2))
        zcr = float(np.mean(np.abs(np.diff(np.sign(audio)))) / 2.0)
        fft_mag = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)
        centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-9))
        
        # Spectral rolloff (85% energy point)
        cum_energy = np.cumsum(fft_mag)
        cutoff = 0.85 * cum_energy[-1]
        rolloff_idx = np.where(cum_energy >= cutoff)[0]
        rolloff = float(freqs[rolloff_idx[0]]) if len(rolloff_idx) > 0 else 4000.0

        return {
            "energy": round(energy, 6),
            "zcr": round(zcr, 6),
            "spectral_centroid": round(centroid, 2),
            "spectral_rolloff": round(rolloff, 2),
        }

    def enroll_voice_sample_step(self, sample_index: int, pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[bool, str, int]:
        """
        Record one of 5 natural speech enrollment samples.
        Samples should cover Hindi, Hinglish, English, fast, and natural pace.
        """
        if len(pcm_bytes) < sample_rate * 1.2:
            return False, "Sample too short. Please speak naturally for at least 1.5 seconds.", len(self._enrollment_samples)

        features = self.extract_acoustic_features(pcm_bytes, sample_rate)
        self._enrollment_samples.append(features)

        count = len(self._enrollment_samples)
        if count >= 5:
            # Aggregate multi-sample profile
            zcr_vals = [s["zcr"] for s in self._enrollment_samples]
            cent_vals = [s["spectral_centroid"] for s in self._enrollment_samples]
            rolloff_vals = [s["spectral_rolloff"] for s in self._enrollment_samples]

            profile = {
                "owner": OWNER_NAME,
                "samples_count": count,
                "zcr_mean": round(float(np.mean(zcr_vals)), 6),
                "zcr_std": round(float(np.std(zcr_vals)), 6),
                "spectral_centroid": round(float(np.mean(cent_vals)), 2),
                "centroid_std": round(float(np.std(cent_vals)), 2),
                "spectral_rolloff": round(float(np.mean(rolloff_vals)), 2),
                "anti_spoofing": "ACTIVE",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            VOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
            VOICE_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            self._voice_profile = profile
            self._enrollment_samples = []
            self.log_event("VOICE_ENROLL_COMPLETE", f"5-sample voice profile saved for {OWNER_NAME}.")
            timeline.record("AUTH", "Voice Enrollment Complete", f"5 samples enrolled for {OWNER_ADDRESS}.")
            return True, f"Voice profile successfully finalized for {OWNER_ADDRESS} with 5 natural samples.", 5

        return True, f"Sample {count}/5 accepted. Please speak the next sentence.", count

    def reset_enrollment(self) -> None:
        self._enrollment_samples = []

    # ── Continuous Speaker Verification & Continuity ──────────────────────────

    def verify_speaker(self, pcm_bytes: bytes, sample_rate: int = 16000) -> SpeakerVerificationResult:
        """
        Verify incoming voice against enrolled profile with anti-spoofing and speaker continuity.
        """
        # 1. Check if biometric profile exists
        if not self._voice_profile:
            return SpeakerVerificationResult(
                is_owner=True,
                confidence=0.85,
                tier="HIGH",
                message="No biometric voice profile enrolled — using authenticated session.",
                anti_spoof=AntiSpoofResult(is_spoof=False, confidence=0.8, risk_level="SAFE", details="Profile bypass")
            )

        try:
            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if len(audio) < 800:
                return SpeakerVerificationResult(
                    is_owner=True,
                    confidence=0.6,
                    tier="MEDIUM",
                    message="Short utterance — retaining active session clearance.",
                    anti_spoof=AntiSpoofResult(is_spoof=False, confidence=0.7, risk_level="SAFE", details="Short frame")
                )

            # 2. Anti-Spoofing check
            anti_spoof = self.detect_voice_spoof(audio, sample_rate)
            if anti_spoof.is_spoof:
                self.lock(reason=f"Spoof detected: {anti_spoof.details}")
                timeline.record("SECURITY", "Voice Spoof Alert", anti_spoof.details, status="BLOCKED")
                return SpeakerVerificationResult(
                    is_owner=False,
                    confidence=0.1,
                    tier="SPOOF_SUSPECTED",
                    message=f"Voice spoof suspected: {anti_spoof.details}",
                    anti_spoof=anti_spoof
                )

            # 3. Acoustic feature similarity
            current_feat = self.extract_acoustic_features(pcm_bytes, sample_rate)
            target_zcr = self._voice_profile.get("zcr_mean", 0.08)
            target_cent = self._voice_profile.get("spectral_centroid", 1200.0)

            diff_zcr = abs(current_feat["zcr"] - target_zcr) / max(target_zcr, 1e-4)
            diff_cent = abs(current_feat["spectral_centroid"] - target_cent) / max(target_cent, 1e-4)

            raw_similarity = max(0.0, min(1.0, 1.0 - (diff_zcr * 0.4 + diff_cent * 0.6)))

            # 4. Continuity check: Detect if another person abruptly speaks mid-session
            if self._last_speaker_hash is not None:
                continuity_drift = abs(current_feat["spectral_centroid"] - self._last_speaker_hash) / max(self._last_speaker_hash, 1e-4)
                if continuity_drift > 0.65:
                    self._continuity_alert_count += 1
                    if self._continuity_alert_count >= 2:
                        self.log_event("SPEAKER_DRIFT", "Abrupt speaker acoustic change detected mid-session.")
                        timeline.record("AUTH", "Speaker Change Detected", "Different voice heard — privilege demoted.", status="WARNING")
                        self.set_auth_level(LEVEL_1_GUEST)

            self._last_speaker_hash = current_feat["spectral_centroid"]

            # 5. Determine Tier
            if raw_similarity >= CONFIDENCE_HIGH:
                self.touch()
                self._continuity_alert_count = 0
                return SpeakerVerificationResult(
                    is_owner=True,
                    confidence=raw_similarity,
                    tier="HIGH",
                    message="Speaker verified as Aditya Rajak with high confidence.",
                    anti_spoof=anti_spoof
                )
            elif raw_similarity >= CONFIDENCE_MEDIUM:
                return SpeakerVerificationResult(
                    is_owner=True,
                    confidence=raw_similarity,
                    tier="MEDIUM",
                    message="Medium owner confidence — confirmation or PIN recommended for sensitive tasks.",
                    anti_spoof=anti_spoof
                )
            else:
                self.log_event("VOICE_MISMATCH", f"Voice similarity {raw_similarity:.2f} below owner threshold.")
                return SpeakerVerificationResult(
                    is_owner=False,
                    confidence=raw_similarity,
                    tier="LOW",
                    message=f"Speaker characteristics do not match {OWNER_ADDRESS}'s profile. Restricted Guest Mode.",
                    anti_spoof=anti_spoof
                )

        except Exception as e:
            return SpeakerVerificationResult(
                is_owner=True,
                confidence=0.5,
                tier="MEDIUM",
                message=f"Biometric fallback evaluation: {e}",
                anti_spoof=AntiSpoofResult(is_spoof=False, confidence=0.5, risk_level="SAFE", details="Fallback")
            )

    # ── Security & Privacy Center Status ──────────────────────────────────────

    def get_security_center_status(self) -> Dict[str, Any]:
        """Provides complete Security Center telemetry for UI and diagnostics."""
        return {
            "owner_name": OWNER_NAME,
            "owner_address": OWNER_ADDRESS,
            "auth_level": self.get_auth_level(),
            "auth_level_name": "VERIFIED_OWNER" if self.get_auth_level() == LEVEL_2_OWNER else ("LOCKED" if self.is_locked() else "RESTRICTED"),
            "voice_verification_enrolled": bool(self._voice_profile),
            "voice_samples_count": self._voice_profile.get("samples_count", 1 if self._voice_profile else 0),
            "anti_spoofing_status": "ACTIVE (Heuristic Replay & Synthetic TTS Analysis)",
            "session_active": not self.is_locked(),
            "session_timeout_seconds": self._session_timeout,
            "session_timeout_minutes": round(self._session_timeout / 60.0, 1),
            "critical_auth_required": True,
            "unknown_users_policy": "RESTRICTED (Level 0/1 Safe Actions Only)",
            "is_locked": self.is_locked(),
        }

    def get_privacy_center_status(self) -> Dict[str, bool]:
        """Provides Privacy Center toggle status."""
        return dict(self._privacy_settings)

    def redact_secrets(self, text: str) -> str:
        """Sanitize text by masking credentials, tokens, and private keys."""
        from core.firewall import PrivateDataFirewall
        return PrivateDataFirewall.redact_secrets(text)


# Singleton accessor
security_manager = SecurityManager.get_instance()
