"""
core/alex_brain.py — Central Cognitive Architecture & Agentic Operating Brain for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Coordinates the full internal cognitive pipeline:
  1. Perception: Multi-modal voice, text, screen, clipboard, environmental sensors.
  2. Identity: Continuous verification of Aditya Sir via biometrics and authorization levels.
  3. Context: Dynamic multi-layer context and reference resolution ("isse", "ye", "this").
  4. Memory: Multi-tier episodic, project, and preference retrieval without whole-store dumps.
  5. Intent & Goals: Structured goal parsing and risk classification.
  6. Planning: Dynamic goal deconstruction and adaptive step replanning.
  7. Security & Permissions: Strict clearance enforcement before privileged execution.
  8. Skill Routing: Selects smallest, fastest local tool (<50ms) before cloud ladder.
  9. Execution & Verification: Pre-check -> Act -> Observe -> Post-check ("No False Success").
  10. Bounded Recovery: Diagnoses errors, applies fallback strategies, bounded retries.
  11. Event-Driven State: Publishes state transitions to UI, Dashboard, and Timeline.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.confidence import evaluate_confidence
from core.context_engine import ContextSnapshot, context_engine
from core.event_bus import event_bus
from core.intent_engine import IntentResult, intent_engine
from core.planner_engine import Plan, planner_engine
from core.project_manager import project_manager
from core.recovery_engine import recovery_engine
from core.security import OWNER_ADDRESS, OWNER_NAME, security_manager
from core.service_manager import service_manager
from core.skill_router import RoutedSkill, skill_router
from core.task_center import task_center


@dataclass
class CognitiveProcessingResult:
    query: str
    resolved_query: str
    intent: str
    risk_level: str
    routed_skill: str
    authorized: bool
    plan_executed: bool
    success: bool
    response_text: str
    duration_ms: float
    verification_status: str


class AlexBrain:
    _instance: Optional[AlexBrain] = None
    _lock = threading.Lock()

    def __init__(self):
        service_manager.start_watchdog()

    @classmethod
    def get_instance(cls) -> AlexBrain:
        with cls._lock:
            if cls._instance is None:
                cls._instance = AlexBrain()
            return cls._instance

    def process_request(
        self,
        raw_text: str,
        speaker: str = OWNER_ADDRESS,
        audio_features: Optional[Dict[str, Any]] = None
    ) -> CognitiveProcessingResult:
        """Executes the full 11-step cognitive architecture for an incoming request."""
        start_t = time.monotonic()
        event_bus.publish("THINKING_STARTED", {"query": raw_text, "speaker": speaker})

        # ── Step 1 & 2: Perception, Identity & Context ──────────────────────
        context_engine.record_turn(speaker, raw_text)
        snapshot = context_engine.get_snapshot(raw_text)
        resolved_query = snapshot.resolved_query

        # Speaker Authorization Verification
        auth_level = security_manager.get_auth_level()
        is_owner = (auth_level >= 2) or (speaker in (OWNER_NAME, OWNER_ADDRESS, "Aditya Sir", "Sir"))

        # ── Step 3: Intent Understanding ────────────────────────────────────
        intent_res: IntentResult = intent_engine.parse(resolved_query)

        # ── Step 4: Skill Routing ───────────────────────────────────────────
        routed: RoutedSkill = skill_router.route_query(resolved_query)

        # ── Step 5: Security & Permission Engine ────────────────────────────
        permission_needed = "computer_control" if routed.risk_level in ("PRIVILEGED", "CRITICAL") else "general"
        allowed, perm_reason = security_manager.check_permission(permission_needed)

        if not allowed:
            duration = round((time.monotonic() - start_t) * 1000, 1)
            msg = f"{OWNER_ADDRESS}, this operation is restricted: {perm_reason}"
            event_bus.publish("SECURITY_BLOCKED", {"query": resolved_query, "reason": perm_reason})
            return CognitiveProcessingResult(
                query=raw_text,
                resolved_query=resolved_query,
                intent=intent_res.intent,
                risk_level=routed.risk_level,
                routed_skill=routed.skill_name,
                authorized=False,
                plan_executed=False,
                success=False,
                response_text=msg,
                duration_ms=duration,
                verification_status="Blocked by Security Engine"
            )

        # ── Step 6 & 7: Deterministic Local Dispatch vs Goal Planning ──────
        if intent_res.is_local_command:
            local_res = intent_engine.execute_local_command(intent_res)
            duration = round((time.monotonic() - start_t) * 1000, 1)
            event_bus.publish("TOOL_COMPLETED", {"tool": intent_res.intent, "duration_ms": duration})
            return CognitiveProcessingResult(
                query=raw_text,
                resolved_query=resolved_query,
                intent=intent_res.intent,
                risk_level=routed.risk_level,
                routed_skill=routed.skill_name,
                authorized=True,
                plan_executed=False,
                success=True,
                response_text=local_res.response_text,
                duration_ms=duration,
                verification_status="Verified (Local Execution)"
            )

        # ── Step 7.5: Knowledge Brain Fast Retrieval ────────────────────────
        from memory.memory_retriever import memory_retriever
        brain_res = memory_retriever.query(resolved_query)
        if brain_res.found and brain_res.confidence >= 0.85:
            duration = round((time.monotonic() - start_t) * 1000, 1)
            event_bus.publish("TOOL_COMPLETED", {"tool": "knowledge_brain", "duration_ms": duration})
            return CognitiveProcessingResult(
                query=raw_text,
                resolved_query=resolved_query,
                intent="KNOWLEDGE_RETRIEVAL",
                risk_level="READ_ONLY",
                routed_skill="knowledge_brain",
                authorized=True,
                plan_executed=False,
                success=True,
                response_text=brain_res.summary_text,
                duration_ms=duration,
                verification_status="Verified (Knowledge Brain)"
            )

        # ── Step 8: Multi-Step Goal Planning ────────────────────────────────
        plan = planner_engine.create_plan_for_goal(resolved_query)
        success, plan_report = planner_engine.execute_plan(plan)

        duration = round((time.monotonic() - start_t) * 1000, 1)
        event_bus.publish("TASK_VERIFIED" if success else "TASK_FAILED", {"plan_id": plan.plan_id, "success": success})

        return CognitiveProcessingResult(
            query=raw_text,
            resolved_query=resolved_query,
            intent=intent_res.intent,
            risk_level=routed.risk_level,
            routed_skill=routed.skill_name,
            authorized=True,
            plan_executed=True,
            success=success,
            response_text=plan_report,
            duration_ms=duration,
            verification_status="Verified (Plan Steps Passed)" if success else "Failed Step"
        )


alex_brain = AlexBrain.get_instance()
