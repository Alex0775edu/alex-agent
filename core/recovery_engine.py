"""
core/recovery_engine.py — Bounded Self-Recovery & Error Diagnosis Engine for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Error Classifications:
  • NETWORK      : DNS timeout, WebSocket drop, rate limit, cloud API 503/504
  • PERMISSION   : Elevation required, file locked, unauthorized speaker
  • FILE         : FileNotFoundError, corrupt payload, access denied
  • APPLICATION  : Process crash, binary missing, port conflict
  • TIMEOUT      : Operation exceeded bounded deadline
  • MODEL        : Quota exhausted (429), token limit, preview API drift
  • BROWSER      : Context crash, selector not found, page timeout
  • UNKNOWN      : Unclassified runtime anomalies

Strategies:
  1. Diagnose -> 2. Select strategy -> 3. Execute recovery (bounded <= 2 retries) -> 4. Report honestly.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.event_bus import event_bus

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ERROR_MEMORY_FILE = CONFIG_DIR / "failure_memory.json"


@dataclass
class FailureRecord:
    category: str
    error_summary: str
    context: str
    suggested_fix: str
    occurrences: int = 1
    last_seen: float = field(default_factory=time.time)


class RecoveryEngine:
    _instance: Optional[RecoveryEngine] = None
    _lock = threading.Lock()

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._failure_memory: Dict[str, FailureRecord] = self._load_failure_memory()

    @classmethod
    def get_instance(cls) -> RecoveryEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = RecoveryEngine()
            return cls._instance

    def _load_failure_memory(self) -> Dict[str, FailureRecord]:
        if ERROR_MEMORY_FILE.exists():
            try:
                import json
                data = json.loads(ERROR_MEMORY_FILE.read_text(encoding="utf-8"))
                return {k: FailureRecord(**v) for k, v in data.items()}
            except Exception:
                pass
        return {}

    def _save_failure_memory(self) -> None:
        try:
            import json
            payload = {k: asdict(v) for k, v in self._failure_memory.items()}
            ERROR_MEMORY_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def classify_error(self, exc: Exception | str) -> Tuple[str, str]:
        """Classifies error into standardized category and diagnosis."""
        err_str = str(exc).lower()

        if any(w in err_str for w in ("timeout", "timed out", "deadline_exceeded")):
            return "TIMEOUT", "Operation exceeded response deadline. Switch to local cached fallback."
        if any(w in err_str for w in ("getaddrinfo", "cannot connect", "connectionrefused", "offline", "unreachable")):
            return "NETWORK", "Cloud endpoint unreachable. Operating in unblocked Local Mode."
        if any(w in err_str for w in ("permission", "access is denied", "not allowed", "unauthorized")):
            return "PERMISSION", "Operation requires higher authorization or owner elevation."
        if any(w in err_str for w in ("filenotfound", "no such file", "path not found")):
            return "FILE", "Target filesystem path does not exist."
        if any(w in err_str for w in ("429", "resource_exhausted", "quota")):
            return "MODEL", "AI model quota reached. Stepping down to faster offline/fallback model."
        if any(w in err_str for w in ("browser", "playwright", "page closed")):
            return "BROWSER", "Browser context closed or stalled. Resetting automation driver."
        return "UNKNOWN", f"Unclassified anomaly: {str(exc)[:100]}"

    def record_failure(self, category: str, error_summary: str, context: str, fix: str) -> None:
        key = f"{category}:{error_summary[:40]}"
        if key in self._failure_memory:
            rec = self._failure_memory[key]
            rec.occurrences += 1
            rec.last_seen = time.time()
        else:
            self._failure_memory[key] = FailureRecord(category, error_summary, context, fix)
        self._save_failure_memory()

    def attempt_recovery(
        self,
        action_name: str,
        primary_callable: Callable[[], Any],
        fallback_callable: Optional[Callable[[], Any]] = None,
        max_retries: int = 2
    ) -> Tuple[bool, Any, str]:
        """Runs operation with bounded recovery attempts and fallback strategy."""
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                result = primary_callable()
                return True, result, "Operation succeeded."
            except Exception as e:
                last_error = str(e)
                cat, diag = self.classify_error(e)
                timeline.record("RECOVERY", f"Error in {action_name} (Attempt {attempt})", f"[{cat}] {diag}", status="RETRY")
                event_bus.publish("RECOVERY_TRIGGERED", {"action": action_name, "category": cat, "attempt": attempt})
                self.record_failure(cat, str(e), action_name, diag)
                time.sleep(0.08 * attempt)

        # Fallback Strategy if primary failed
        if fallback_callable:
            try:
                res = fallback_callable()
                timeline.record("RECOVERY", f"Fallback used for {action_name}", "Fallback execution verified.", status="SUCCESS")
                return True, res, "Recovered using alternate fallback capability."
            except Exception as fe:
                last_error = str(fe)

        return False, None, f"Recovery bounded threshold exceeded: {last_error}"


recovery_engine = RecoveryEngine.get_instance()

