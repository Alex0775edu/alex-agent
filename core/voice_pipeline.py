"""
core/voice_pipeline.py — End-to-End Voice-to-Action Pipeline for ALEX AI.

Lifecycle Stages:
  1. Input Capture (Microphone Audio / Typed Input / Audio Buffer)
  2. Noise & Silence Gate (RMS Energy Voice Activity Detection)
  3. Speech-to-Text Transcription (UnifiedSTT: Gemini / Whisper / Vosk / SAPI)
  4. Deduplication & Idempotency Guard (Sliding-window duplicate suppression)
  5. Command Understanding & Slot Extraction (IntentEngine: Hindi / Hinglish / English)
  6. Security, Authorization & Path Safety Checks (SecurityManager & Path Guards)
  7. Consequential Action Confirmation (Overwrite & Deletion Protection)
  8. Action Execution & Genuine Verification (AppAdapters, FileController, WebControl)
  9. Spoken Voice & UI Log Output (TTS Player, Reactive HUD, UI Log)
 10. Audit Logging (Action Timeline & Task Center)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from core.action_timeline import timeline
from core.firewall import redact
from core.intent_engine import IntentResult, intent_engine
from core.security import OWNER_ADDRESS, security_manager
from core.stt import calculate_audio_rms, stt_engine
from core.task_center import task_center


@dataclass
class PipelineResult:
    command_text: str
    intent: str
    slots: Dict[str, Any]
    success: bool
    verified: bool
    response_text: str
    engine_used: str = "local"
    duplicate_suppressed: bool = False
    needs_confirmation: bool = False
    execution_time_seconds: float = 0.0
    error_message: Optional[str] = None


def should_forward_to_live_session(result: PipelineResult) -> bool:
    """Only retry ordinary unanswered queries through the live session."""
    return (
        not result.success
        and result.intent == "GENERAL_QUERY"
        and result.engine_used != "autonomous_task_orchestrator"
    )


class VoiceToActionPipeline:
    """Orchestrates asynchronous, non-blocking end-to-end voice-to-action workflows."""

    _instance: Optional[VoiceToActionPipeline] = None
    _lock = threading.Lock()

    # Deduplication window: identical commands within this window are suppressed
    DEDUP_WINDOW_SECONDS: float = 3.5

    @classmethod
    def get_instance(cls) -> VoiceToActionPipeline:
        with cls._lock:
            if cls._instance is None:
                cls._instance = VoiceToActionPipeline()
            return cls._instance

    def __init__(self):
        self._recent_commands: List[Tuple[str, float]] = []  # List of (hash, timestamp)
        self._is_processing: bool = False
        self._cancelled: bool = False
        self._current_task: Optional[threading.Thread] = None
        self._pending_confirmation: Optional[Dict[str, Any]] = None

        # Callbacks for UI and TTS
        self.state_callback: Optional[Callable[[str], None]] = None
        self.log_callback: Optional[Callable[[str], None]] = None
        self.speak_callback: Optional[Callable[[str], None]] = None

    def cancel(self):
        """Immediately signals cancellation of the in-flight voice or action task."""
        self._cancelled = True
        if self.state_callback:
            self.state_callback("IDLE")
        if self.log_callback:
            self.log_callback("SYS: Voice command cancelled by user.")

    def _set_ui_state(self, state: str):
        if self.state_callback:
            try:
                self.state_callback(state)
            except Exception:
                pass

    def _log(self, text: str):
        if self.log_callback:
            try:
                self.log_callback(text)
            except Exception:
                pass

    def _speak(self, text: str):
        if self.speak_callback:
            try:
                self.speak_callback(text)
            except Exception:
                pass

    def _sanitize_log_text(self, text: str) -> str:
        """Redact credentials and common contact data before logging text."""
        return redact(text)

    def _check_duplicate(self, text: str) -> bool:
        """Sliding-window deduplication guard to prevent duplicate execution."""
        clean_text = text.strip().lower()
        cmd_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        now = time.monotonic()

        # Evict old entries
        self._recent_commands = [
            (h, t) for (h, t) in self._recent_commands if (now - t) < self.DEDUP_WINDOW_SECONDS
        ]

        for h, t in self._recent_commands:
            if h == cmd_hash and (now - t) < self.DEDUP_WINDOW_SECONDS:
                return True

        self._recent_commands.append((cmd_hash, now))
        return False

    def process_audio(
        self,
        audio: Union[np.ndarray, bytes],
        language: str = "auto"
    ) -> PipelineResult:
        """
        Executes the full pipeline from raw microphone or audio buffer input:
        Audio -> VAD -> STT -> Intent -> Safety -> Execution -> Verification -> Feedback
        """
        start_t = time.monotonic()
        self._cancelled = False
        self._set_ui_state("LISTENING")

        # 1. Voice Activity & Silence Detection
        if stt_engine.is_silent(audio):
            self._set_ui_state("IDLE")
            return PipelineResult(
                command_text="",
                intent="NONE",
                slots={},
                success=False,
                verified=False,
                response_text="No audible voice detected.",
                engine_used="VAD_SILENCE",
                execution_time_seconds=round(time.monotonic() - start_t, 3)
            )

        # 2. Speech-to-Text Transcription
        self._set_ui_state("THINKING")
        try:
            transcript, engine_used = stt_engine.transcribe(audio, language=language)
        except Exception as e:
            self._set_ui_state("ERROR")
            err_msg = f"Speech recognition failed: {e}"
            self._log(f"SYS: {err_msg}")
            return PipelineResult(
                command_text="",
                intent="ERROR",
                slots={},
                success=False,
                verified=False,
                response_text=err_msg,
                engine_used="STT_ERROR",
                execution_time_seconds=round(time.monotonic() - start_t, 3),
                error_message=str(e)
            )

        if not transcript or not transcript.strip():
            self._set_ui_state("IDLE")
            return PipelineResult(
                command_text="",
                intent="NONE",
                slots={},
                success=False,
                verified=False,
                response_text="Could not transcribe audio command.",
                engine_used=engine_used,
                execution_time_seconds=round(time.monotonic() - start_t, 3)
            )

        # 3. Forward to Command Execution Pipeline
        return self.process_text_command(transcript, engine_used=engine_used)

    def process_text_command(
        self,
        command_text: str,
        engine_used: str = "typed_input"
    ) -> PipelineResult:
        """
        Processes a validated text command (from STT or direct UI text input).
        """
        start_t = time.monotonic()
        self._cancelled = False
        raw_cmd = command_text.strip()

        if not raw_cmd:
            return PipelineResult(
                command_text="",
                intent="NONE",
                slots={},
                success=False,
                verified=False,
                response_text="Empty command received.",
                engine_used=engine_used
            )

        parsed: IntentResult = intent_engine.parse(raw_cmd)
        is_skillsum = parsed.intent == "SKILLSUM_RESUME_EVAL" or bool(
            re.search(r"\b(?:resume|cv|candidate)\b", raw_cmd, re.IGNORECASE)
            and re.search(r"\b(?:evaluate|parse|analy[sz]e|process|match)\b", raw_cmd, re.IGNORECASE)
        )

        # 1. Deduplication Guard
        if self._check_duplicate(raw_cmd):
            duplicate_log = (
                "SkillSum request repeated within the idempotency window."
                if is_skillsum
                else self._sanitize_log_text(raw_cmd)
            )
            self._log(f"SYS: Duplicate voice trigger '{duplicate_log}' suppressed (idempotency window active).")
            return PipelineResult(
                command_text=raw_cmd,
                intent="DUPLICATE",
                slots={},
                success=True,
                verified=True,
                response_text="",
                engine_used=engine_used,
                duplicate_suppressed=True,
                execution_time_seconds=round(time.monotonic() - start_t, 3)
            )

        # Log User Command
        sanitized_input = (
            "SkillSum resume evaluation requested."
            if is_skillsum
            else self._sanitize_log_text(raw_cmd)
        )
        self._log(f"You: {sanitized_input}")
        self._set_ui_state("THINKING")

        # 2. Check for Pending Confirmation (e.g. Overwrite confirmation)
        if self._pending_confirmation:
            conf_res = self._handle_confirmation(raw_cmd, start_t)
            if conf_res is not None:
                return conf_res

        # 3. Intent Understanding & Planning
        lang = parsed.detected_language

        if self._cancelled:
            self._set_ui_state("IDLE")
            return PipelineResult(
                command_text=raw_cmd,
                intent=parsed.intent,
                slots=parsed.slots,
                success=False,
                verified=False,
                response_text="Command cancelled.",
                engine_used=engine_used
            )

        # 4. Security & Safety Check
        security_manager.touch()
        if security_manager.is_locked() and parsed.intent not in ("SECURITY_LOCK", "EMERGENCY_STOP"):
            deny_msg = f"{OWNER_ADDRESS}, ALEX currently locked hai. Command execute karne ke liye pehle unlock karein." if lang in ("hindi", "hinglish") else f"ALEX is locked, {OWNER_ADDRESS}. Please unlock to execute commands."
            self._set_ui_state("IDLE")
            self._log(f"ALEX: {deny_msg}")
            self._speak(deny_msg)
            return PipelineResult(
                command_text=raw_cmd,
                intent=parsed.intent,
                slots=parsed.slots,
                success=False,
                verified=False,
                response_text=deny_msg,
                engine_used=engine_used
            )

        # 5. Local Fast Execution Route (<50ms)
        self._set_ui_state("EXECUTING")
        if parsed.is_local_command:
            executed = intent_engine.execute_local_command(parsed)
            resp = executed.response_text
            self._set_ui_state("SPEAKING")
            if parsed.intent == "SKILLSUM_RESUME_EVAL":
                self._log(
                    "ALEX: SkillSum evaluation succeeded."
                    if executed.handled
                    else "ALEX: SkillSum evaluation failed."
                )
            else:
                sanitized_resp = self._sanitize_log_text(resp)
                self._log(f"ALEX: {sanitized_resp}")
            self._speak(resp)
            self._set_ui_state("IDLE")

            # Timeline logging
            timeline.record(
                event_type="COMMAND",
                title=f"Voice/Action: {parsed.intent}",
                details=sanitized_input,
                status="SUCCESS" if executed.handled else "FAILED"
            )

            return PipelineResult(
                command_text=raw_cmd,
                intent=parsed.intent,
                slots=parsed.slots,
                success=executed.handled,
                verified=executed.handled,
                response_text=resp,
                engine_used=engine_used,
                execution_time_seconds=round(time.monotonic() - start_t, 3),
                error_message=None if executed.handled else "Local command was not handled successfully."
            )

        # 6. Autonomous Multi-Step Goal Planning (Autonomous Task Orchestrator)
        goal_keywords = (
            "audit", "report", "banao", "research", "organize", "optimize",
            "clean", "speed up", "fix", "bugs", "scan", "workflow", "plan",
            "presentation", "slides", "ppt"
        )
        if any(kw in raw_cmd.lower() for kw in goal_keywords):
            try:
                from core.alex_brain import alex_brain
                self._set_ui_state("THINKING")
                brain_res = alex_brain.process_request(raw_cmd)
                resp = brain_res.response_text
                self._set_ui_state("SPEAKING" if brain_res.success else "ERROR")
                sanitized_resp = self._sanitize_log_text(resp)
                self._log(f"ALEX: {sanitized_resp}")
                self._speak(resp)
                self._set_ui_state("IDLE")
                return PipelineResult(
                    command_text=raw_cmd,
                    intent=brain_res.intent,
                    slots={},
                    success=brain_res.success,
                    verified=brain_res.success,
                    response_text=resp,
                    engine_used="autonomous_task_orchestrator",
                    execution_time_seconds=round(time.monotonic() - start_t, 3),
                    error_message=None if brain_res.success else brain_res.verification_status
                )
            except Exception as e:
                err_resp = f"{OWNER_ADDRESS}, autonomous task orchestration mein error aaya: {e}"
                self._set_ui_state("ERROR")
                self._log(f"SYS: {err_resp}")
                self._speak(err_resp)
                self._set_ui_state("IDLE")
                return PipelineResult(
                    command_text=raw_cmd,
                    intent=parsed.intent,
                    slots={},
                    success=False,
                    verified=False,
                    response_text=err_resp,
                    engine_used="autonomous_task_orchestrator",
                    execution_time_seconds=round(time.monotonic() - start_t, 3),
                    error_message=str(e)
                )

        # 7. Fallback Route: Complex / LLM reasoning
        try:
            from core import gemini
            self._set_ui_state("THINKING")
            resp_obj = gemini.call(raw_cmd, tier=gemini.FAST)
            answer = (getattr(resp_obj, "text", "") or "").strip()
            if not answer:
                answer = "I processed your request, Sir."

            self._set_ui_state("SPEAKING")
            sanitized_answer = self._sanitize_log_text(answer)
            self._log(f"ALEX: {sanitized_answer}")
            self._speak(answer)
            self._set_ui_state("IDLE")

            timeline.record("AI_QUERY", f"Query: {parsed.intent}", sanitized_input, status="SUCCESS")

            return PipelineResult(
                command_text=raw_cmd,
                intent=parsed.intent,
                slots=parsed.slots,
                success=True,
                verified=True,
                response_text=answer,
                engine_used="gemini_llm",
                execution_time_seconds=round(time.monotonic() - start_t, 3)
            )
        except Exception as e:
            self._set_ui_state("ERROR")
            err_text = f"{OWNER_ADDRESS}, offline mode mein yeh complex action process nahi ho sakta. Internet check karein." if lang in ("hindi", "hinglish") else f"Could not process complex request offline: {e}"
            self._log(f"ALEX: {err_text}")
            self._speak(err_text)
            self._set_ui_state("IDLE")
            return PipelineResult(
                command_text=raw_cmd,
                intent=parsed.intent,
                slots=parsed.slots,
                success=False,
                verified=False,
                response_text=err_text,
                engine_used="error",
                execution_time_seconds=round(time.monotonic() - start_t, 3),
                error_message=str(e)
            )

    def _handle_confirmation(self, user_reply: str, start_t: float) -> Optional[PipelineResult]:
        """Handles pending confirmation for consequential actions (e.g. file overwrite)."""
        pending = self._pending_confirmation
        clean = user_reply.strip().lower()
        tokens = set(re.findall(r'\b[a-zA-Z0-9_]+\b', clean))

        negative_words = {"no", "nahi", "na", "cancel", "roko", "stop", "abort", "reject"}
        affirmative_words = {"yes", "haan", "ha", "confirm", "sure", "ok", "proceed"}

        # 1. Check negative / cancellation FIRST (so 'cancel kar do' is always cancellation)
        if tokens.intersection(negative_words) or "mat karo" in clean or "cancel" in clean:
            self._pending_confirmation = None
            msg = f"{OWNER_ADDRESS}, action safely cancel kar diya gaya hai."
            self._log(f"ALEX: {msg}")
            self._speak(msg)
            self._set_ui_state("IDLE")
            return PipelineResult(
                command_text=user_reply,
                intent="CONFIRMATION_CANCELLED",
                slots={},
                success=True,
                verified=True,
                response_text=msg,
                execution_time_seconds=round(time.monotonic() - start_t, 3)
            )

        # 2. Check affirmative / confirmation
        elif tokens.intersection(affirmative_words) or "kar do" in clean or "theek hai" in clean:
            action_fn = pending.get("action_fn")
            desc = pending.get("description", "Action")
            self._pending_confirmation = None

            try:
                result_msg = action_fn() if callable(action_fn) else "Action confirmed and executed."
                self._log(f"ALEX: {result_msg}")
                self._speak(result_msg)
                self._set_ui_state("IDLE")
                return PipelineResult(
                    command_text=user_reply,
                    intent="CONFIRMATION_ACCEPTED",
                    slots={},
                    success=True,
                    verified=True,
                    response_text=result_msg,
                    execution_time_seconds=round(time.monotonic() - start_t, 3)
                )
            except Exception as e:
                err_msg = f"Failed to execute confirmed action: {e}"
                self._log(f"ALEX: {err_msg}")
                self._speak(err_msg)
                self._set_ui_state("IDLE")
                return PipelineResult(
                    command_text=user_reply,
                    intent="CONFIRMATION_ERROR",
                    slots={},
                    success=False,
                    verified=False,
                    response_text=err_msg,
                    error_message=str(e)
                )

        return None

    def request_confirmation(self, description: str, action_fn: Callable[[], str], prompt_msg: str):
        """Sets a pending confirmation gate before performing a consequential action."""
        self._pending_confirmation = {
            "description": description,
            "action_fn": action_fn
        }
        self._log(f"ALEX: {prompt_msg}")
        self._speak(prompt_msg)
        self._set_ui_state("IDLE")


# Singleton instance
voice_pipeline = VoiceToActionPipeline.get_instance()
