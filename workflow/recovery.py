"""
workflow/recovery.py — Error Classification, Exponential Backoff & Rollback Engine.

Enforces:
  • Failure classification: TRANSIENT vs PERMANENT vs PERMISSION vs TIMEOUT
  • Idempotency guards: Prevents automatic retries for irreversible operations
  • Exponential backoff calculation for transient network/file lock retries
  • Safe alternative skill resolution
  • Partial change rollback on task failures

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from workflow.models import FailureType, TaskStatus, WorkflowTask


class RecoveryEngine:
    """Manages failure analysis, bounded retries, and rollback strategies."""

    # Map of fallback alternative skills
    SKILL_ALTERNATIVES = {
        "web_research": "deep_research",
        "deep_research": "web_research",
        "code_helper": "dev_agent",
        "dev_agent": "code_helper",
        "file_processor": "document_creator",
        "system_monitor": "computer_settings"
    }

    @staticmethod
    def classify_failure(error: Any, task: WorkflowTask) -> FailureType:
        """Classifies the failure category based on error message and context."""
        err_str = str(error).lower()

        if "permission" in err_str or "clearance" in err_str or "unauthorized" in err_str:
            return FailureType.PERMISSION_DENIED

        if "missing" in err_str and ("dependency" in err_str or "package" in err_str or "module" in err_str):
            return FailureType.DEPENDENCY_MISSING

        if "timed out" in err_str or "timeout" in err_str:
            return FailureType.TIMEOUT

        if "verification" in err_str or "empty" in err_str or "0 bytes" in err_str:
            return FailureType.VERIFICATION_FAILED

        # Transient network, lock, or busy errors
        transient_tokens = ("busy", "locked", "connection reset", "temporarily unavailable", "retry", "rate limit", "503", "504", "winerror 32")
        if any(t in err_str for t in transient_tokens):
            return FailureType.TRANSIENT

        return FailureType.PERMANENT

    @staticmethod
    def calculate_backoff_seconds(retry_count: int, base_seconds: float = 0.1, max_backoff: float = 3.0) -> float:
        """Calculates exponential backoff delay: base * 2^retry_count."""
        delay = base_seconds * (2 ** max(0, retry_count))
        return min(max_backoff, delay)

    def can_safely_retry(self, task: WorkflowTask, failure_type: FailureType) -> Tuple[bool, str]:
        """
        Idempotency guard: Determines if the task can be safely retried automatically.
        """
        # 1. Irreversible action protection
        if task.is_irreversible:
            return False, "Action is irreversible (e.g. deletion, external message). Automatic retry blocked."

        # 2. Retry count limits
        if task.retry_count >= task.max_retries:
            return False, f"Task exceeded maximum retry attempts limit ({task.max_retries})."

        # 3. Permanent failure rejection
        if failure_type in (
            FailureType.PERMANENT,
            FailureType.PERMISSION_DENIED,
            FailureType.DEPENDENCY_MISSING
        ):
            return False, f"Failure type '{failure_type.value}' is non-transient and cannot be resolved by retry."

        # Transient or timeout failures can be retried
        return True, "Safe to retry with exponential backoff."

    def get_alternative_skill(self, skill_id: str) -> Optional[str]:
        """Finds a compatible alternative skill if primary fails."""
        return self.SKILL_ALTERNATIVES.get(skill_id)

    @staticmethod
    def rollback_partial_files(file_paths: List[str]) -> List[str]:
        """Safely rolls back partially created temporary files upon failure."""
        rolled_back = []
        for fp in file_paths:
            try:
                p = Path(fp)
                if p.exists() and p.is_file():
                    p.unlink()
                    rolled_back.append(str(p))
            except Exception:
                pass
        return rolled_back


# Singleton Instance
recovery_engine = RecoveryEngine()

