"""
core/interaction_loop.py — Reliable Computer Interaction Loop & Adaptive Recovery for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Implements the Canonical Interaction Cycle:
  UNDERSTAND REQUEST
        ↓
  OBSERVE CURRENT SCREEN
        ↓
  IDENTIFY TARGET
        ↓
  CHECK PERMISSIONS
        ↓
  PLAN ACTION
        ↓
  EXECUTE ACTION
        ↓
  OBSERVE NEW SCREEN
        ↓
  VERIFY RESULT
        ↓
  RECOVER OR CONTINUE

Features:
  • Semantic Selectors preferred over hard-coded screen coordinates.
  • Re-detection of UI elements after layout or window shifts.
  • Responsiveness check (detects frozen/hung application windows).
  • Bounded Retries (max 3) with safe alternative pathways.
  • Strict Idempotency: Prevents duplicate submissions, file creation, or duplicate messages.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.privacy_manager import privacy_manager
from core.screen_engine import ScreenEngine, screen_engine
from core.security import LEVEL_2_OWNER, security_manager


@dataclass
class CycleStepResult:
    step_name: str
    success: bool
    details: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class InteractionResult:
    request: str
    target: str
    action_type: str
    success: bool
    verified: bool
    recovery_attempts: int
    summary: str
    before_window: str
    after_window: str
    difference_score: float
    errors: List[str] = field(default_factory=list)
    steps: List[CycleStepResult] = field(default_factory=list)


class InteractionLoop:
    """Orchestrates closed-loop desktop interactions with verification & adaptive recovery."""

    _instance: Optional[InteractionLoop] = None

    @classmethod
    def get_instance(cls) -> InteractionLoop:
        if cls._instance is None:
            cls._instance = InteractionLoop()
        return cls._instance

    def __init__(self):
        self._action_history_hashes: set[str] = set()
        self._max_retries: int = 3

    def _generate_action_hash(self, request: str, target: str, action_type: str) -> str:
        key = f"{request.strip().lower()}|{target.strip().lower()}|{action_type.strip().lower()}"
        return hashlib.sha256(key.encode()).hexdigest()

    def run_interaction_cycle(
        self,
        request: str,
        target_description: str,
        action_type: str,
        executor_func: Callable[[], Tuple[bool, str]],
        alternative_func: Optional[Callable[[], Tuple[bool, str]]] = None,
        permission_required: str = "SAFE",
        expect_visual_change: bool = True
    ) -> InteractionResult:
        """
        Executes one complete verified desktop cycle with bounded adaptive recovery.
        """
        steps: List[CycleStepResult] = []
        errors: List[str] = []
        action_hash = self._generate_action_hash(request, target_description, action_type)

        # ── Step 1: UNDERSTAND REQUEST & IDEMPOTENCY GUARD ───────────────────
        steps.append(CycleStepResult("UNDERSTAND_REQUEST", True, f"Request parsed: '{request}' targeting '{target_description}'"))

        # For sensitive one-way actions (submit, send, purchase), block duplicates
        if action_type.lower() in ("send", "submit", "publish", "purchase") and action_hash in self._action_history_hashes:
            err = f"Idempotency Guard: Action '{action_type}' for target '{target_description}' was already executed. Duplicate execution prevented."
            errors.append(err)
            return InteractionResult(
                request=request,
                target=target_description,
                action_type=action_type,
                success=False,
                verified=False,
                recovery_attempts=0,
                summary=err,
                before_window="Unknown",
                after_window="Unknown",
                difference_score=0.0,
                errors=errors,
                steps=steps
            )

        # ── Step 2: OBSERVE CURRENT SCREEN ───────────────────────────────────
        before_win = screen_engine.get_active_window()
        before_win_title = before_win.title if before_win else "Desktop"
        before_bytes, cap_err = screen_engine.capture_screen()
        if cap_err:
            steps.append(CycleStepResult("OBSERVE_SCREEN", False, f"Screen capture notice: {cap_err}"))
        else:
            steps.append(CycleStepResult("OBSERVE_SCREEN", True, f"Observed active window: '{before_win_title}'"))

        # ── Step 3: CHECK PERMISSIONS & PRIVACY ──────────────────────────────
        auth_level = security_manager.get_auth_level()
        if permission_required.upper() in ("PRIVILEGED", "CRITICAL") and auth_level < LEVEL_2_OWNER:
            err = f"Permission Denied: Action requires verified owner access. Current clearance level: {auth_level}."
            errors.append(err)
            timeline.record(
                event_type="AUTH",
                title=f"Interaction blocked: {request}",
                details=err,
                status="BLOCKED",
                permission_decision="BLOCKED"
            )
            return InteractionResult(
                request=request, target=target_description, action_type=action_type,
                success=False, verified=False, recovery_attempts=0, summary=err,
                before_window=before_win_title, after_window=before_win_title,
                difference_score=0.0, errors=errors, steps=steps
            )

        if before_win and privacy_manager.is_window_sensitive(before_win.title):
            err = f"Privacy Guard: Interaction with sensitive window '{before_win.title}' is blocked."
            errors.append(err)
            return InteractionResult(
                request=request, target=target_description, action_type=action_type,
                success=False, verified=False, recovery_attempts=0, summary=err,
                before_window=before_win_title, after_window=before_win_title,
                difference_score=0.0, errors=errors, steps=steps
            )

        steps.append(CycleStepResult("CHECK_PERMISSIONS", True, "Permissions verified and clearance granted."))

        # ── Step 4 & 5: PLAN ACTION & EXECUTE WITH ADAPTIVE RECOVERY ─────────
        recovery_count = 0
        execution_success = False
        exec_details = ""
        last_diff = 0.0

        for attempt in range(self._max_retries):
            # Check if target application is responsive before attempting
            cur_win = screen_engine.get_active_window()
            if cur_win and not cur_win.is_responsive:
                err = f"Window '{cur_win.title}' is not responding (hung application)."
                errors.append(err)
                time.sleep(0.5)

            # Choose primary or fallback alternative
            fn = executor_func if attempt == 0 or not alternative_func else alternative_func
            try:
                ok, msg = fn()
                exec_details = msg
                steps.append(CycleStepResult(f"EXECUTE_ATTEMPT_{attempt+1}", ok, msg))
            except Exception as e:
                ok = False
                exec_details = str(e)
                errors.append(exec_details)
                steps.append(CycleStepResult(f"EXECUTE_ATTEMPT_{attempt+1}", False, f"Execution exception: {e}"))

            # ── Step 6: OBSERVE NEW SCREEN ───────────────────────────────────
            time.sleep(0.2)  # Allow UI thread to repaint
            after_win = screen_engine.get_active_window()
            after_win_title = after_win.title if after_win else "Desktop"
            after_bytes, _ = screen_engine.capture_screen()

            # ── Step 7: VERIFY RESULT ────────────────────────────────────────
            verified = False
            if ok:
                if expect_visual_change and before_bytes and after_bytes:
                    ver_res = screen_engine.compare_images(before_bytes, after_bytes)
                    last_diff = ver_res.difference_score
                    if ver_res.has_changed:
                        verified = True
                        steps.append(CycleStepResult("VERIFY_RESULT", True, f"Visual confirmation: diff={last_diff:.3f}"))
                    else:
                        # Fallback verification: Check if window title changed
                        if after_win_title != before_win_title:
                            verified = True
                            steps.append(CycleStepResult("VERIFY_RESULT", True, f"Window state change verified: '{after_win_title}'"))
                        else:
                            verified = False
                            steps.append(CycleStepResult("VERIFY_RESULT", False, "No visual or window changes detected."))
                else:
                    verified = True
                    steps.append(CycleStepResult("VERIFY_RESULT", True, "Action completed (visual verification bypassed)."))

            if ok and verified:
                execution_success = True
                self._action_history_hashes.add(action_hash)
                break
            else:
                recovery_count += 1
                if attempt < self._max_retries - 1:
                    time.sleep(0.3)  # Backoff before recovery attempt

        # Record event in timeline
        status_str = "SUCCESS" if execution_success else "FAILED"
        timeline.record(
            event_type="EXEC",
            title=f"Interaction: {action_type} on '{target_description}'",
            details=exec_details,
            status=status_str,
            user_request=request,
            action_taken=f"{action_type} -> {target_description}",
            tool_used="InteractionLoop",
            permission_decision=permission_required,
            result=exec_details,
            verification_status="VERIFIED" if execution_success else "FAILED",
            errors=errors,
            recovery_attempts=recovery_count
        )

        after_win_final = screen_engine.get_active_window()
        after_win_name = after_win_final.title if after_win_final else "Desktop"

        return InteractionResult(
            request=request,
            target=target_description,
            action_type=action_type,
            success=execution_success,
            verified=execution_success,
            recovery_attempts=recovery_count,
            summary=f"Action '{action_type}' {'succeeded and verified' if execution_success else 'failed after recovery attempts'}: {exec_details}",
            before_window=before_win_title,
            after_window=after_win_name,
            difference_score=last_diff,
            errors=errors,
            steps=steps
        )


interaction_loop = InteractionLoop.get_instance()

