"""
core/planner_engine.py — Dependency-Aware Goal-to-Plan Orchestrator for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Capabilities:
  • Transforms abstract natural goals into structured, executable steps.
  • Dependency-aware step ordering (depends_on field).
  • Real action dispatch via task_dispatcher — no simulation.
  • Bounded retry (max 2) for transient failures.
  • Cancellation propagation via threading.Event.
  • Duplicate concurrent execution guard (same plan_id cannot run twice).
  • Confirms PRIVILEGED/CRITICAL steps through task_center autonomy gate.
  • Records every step outcome in the audit timeline.
  • Never marks a step VERIFIED without real evidence from the handler.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.action_timeline import timeline
from core.event_bus import event_bus
from core.security import OWNER_ADDRESS, security_manager
from core.task_center import TaskStatus, task_center

BASE_DIR = Path(__file__).resolve().parent.parent

MAX_RETRIES = 2
STEP_TIMEOUT_SEC = 120  # per step


@dataclass
class PlanStep:
    step_id: int
    description: str
    skill_name: str
    action_name: str
    params: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)   # step_ids that must be VERIFIED first
    risk_level: str = "SAFE"         # SAFE | PRIVILEGED | CRITICAL
    status: str = "PENDING"          # PENDING | EXECUTING | VERIFIED | FAILED | SKIPPED | RETRIED | CANCELLED
    result_details: str = ""
    error_message: str = ""
    retry_count: int = 0
    generated_files: List[str] = field(default_factory=list)


@dataclass
class Plan:
    plan_id: str
    goal: str
    target: str
    steps: List[PlanStep]
    created_at: float = field(default_factory=time.time)
    status: str = "CREATED"   # CREATED | RUNNING | COMPLETED | FAILED | PAUSED | CANCELLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "target": self.target,
            "status": self.status,
            "steps": [asdict(s) for s in self.steps],
        }


class PlannerEngine:
    _instance: Optional[PlannerEngine] = None
    _class_lock = threading.Lock()

    # Tracks plan_ids currently executing — prevents duplicate concurrent runs
    _running_plans: Set[str] = set()
    _running_lock = threading.Lock()

    def __init__(self):
        self._plan_cancel_events: Dict[str, threading.Event] = {}

    @classmethod
    def get_instance(cls) -> PlannerEngine:
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = PlannerEngine()
        return cls._instance

    # ── Plan Construction ─────────────────────────────────────────────────────

    def create_plan_for_goal(self, goal: str, target: str = "") -> Plan:
        """Deconstructs a high-level user goal into concrete, dependency-ordered steps."""
        plan_id = f"PLAN-{int(time.time() * 1000) % 100000}"
        g_lower = goal.lower().strip()
        steps: List[PlanStep] = []

        # 1. Project Audit
        if any(w in g_lower for w in ("audit", "website check", "site check", "project check")):
            proj_name = target or "alex"
            steps = [
                PlanStep(1, f"Identify workspace & repository for '{proj_name}'", "projects", "get_context",
                         {"project": proj_name}, depends_on=[]),
                PlanStep(2, "Capture a local system resource snapshot", "system", "audit_resources",
                         {}, depends_on=[1]),
                PlanStep(3, "Scan project source code syntax & file structure", "coding", "syntax_audit",
                         {"project": proj_name}, depends_on=[1]),
                PlanStep(4, "Inspect security permissions & environment secrets", "system", "security_audit",
                         {}, risk_level="PRIVILEGED", depends_on=[1]),
                PlanStep(5, "Compile comprehensive verification report & save deliverable", "documents", "generate_summary",
                         {"goal": goal, "project": proj_name, "save_report": True}, depends_on=[2, 3, 4]),
                PlanStep(6, "Verify generated report exists on disk and is non-empty", "system", "verify_result",
                         {"goal": goal, "project": proj_name}, depends_on=[5]),
            ]

        # 2. Research + Report
        elif any(w in g_lower for w in ("research", "research karo", "dhundo")):
            topic = target or goal
            steps = [
                PlanStep(1, f"Multi-source research on '{topic}'", "research", "deep_research",
                         {"topic": topic}, depends_on=[]),
                PlanStep(2, "Synthesize findings into structured summary", "documents", "generate_summary",
                         {"goal": goal}, depends_on=[1]),
            ]

        # 3. System Performance Optimization
        elif any(w in g_lower for w in ("fast", "optimize", "speed up", "clean", "performance")):
            steps = [
                PlanStep(1, "Audit CPU, RAM, and disk capacity", "system", "audit_resources", {}, depends_on=[]),
                PlanStep(2, "Inspect heavy background processes", "system", "list_heavy_processes", {}, depends_on=[1]),
                PlanStep(3, "Analyze Windows startup applications", "system", "check_startup_apps", {}, depends_on=[1]),
                PlanStep(4, "Clean temporary caches & safe system artifacts", "files", "clean_temp_cache",
                         {}, risk_level="PRIVILEGED", depends_on=[1, 2]),
                PlanStep(5, "Verify system responsiveness and report recommendations", "system", "verify_telemetry",
                         {}, depends_on=[4]),
            ]

        # 4. Downloads Organization
        elif "download" in g_lower and any(w in g_lower for w in ("organize", "sort", "arrange")):
            steps = [
                PlanStep(1, "Scan Downloads directory items & file extensions", "files", "scan_downloads",
                         {}, depends_on=[]),
                PlanStep(2, "Categorize into Documents, Images, Installers, Code, Media", "files", "build_categories",
                         {}, depends_on=[1]),
                PlanStep(3, "Safely move items into dedicated folders", "files", "move_files",
                         {}, risk_level="PRIVILEGED", depends_on=[2]),
                PlanStep(4, "Verify directory structure and destination file integrity", "files", "verify_structure",
                         {}, depends_on=[3]),
            ]

        # 5. Presentation Creation
        elif any(w in g_lower for w in ("ppt", "presentation", "powerpoint", "slides", "slide")):
            topic = target or goal
            steps = [
                PlanStep(1, f"Research and outline content for '{topic}'", "research", "deep_research",
                         {"topic": topic}, depends_on=[]),
                PlanStep(2, f"Build PowerPoint presentation on '{topic}'", "documents", "run_presentation",
                         {"topic": topic}, depends_on=[1]),
            ]

        # 6. Dev Bug Audit + Report
        elif any(w in g_lower for w in ("bug", "bugs", "fix", "test", "dev audit", "code audit")):
            proj = target or "alex"
            steps = [
                PlanStep(1, f"Syntax audit for project '{proj}'", "coding", "syntax_audit",
                         {"project": proj}, depends_on=[]),
                PlanStep(2, f"Run dev workflow for '{proj}'", "coding", "run_dev_audit",
                         {"project": proj}, depends_on=[1]),
                PlanStep(3, "Generate bug report summary", "documents", "generate_summary",
                         {"goal": goal, "project": proj}, depends_on=[2]),
            ]

        # 7. Universal Fallback
        else:
            steps = [
                PlanStep(1, f"Analyze requirements for: '{goal}'", "system", "analyze_intent",
                         {"goal": goal}, depends_on=[]),
                PlanStep(2, "Execute requested operation safely", "system", "execute_operation",
                         {"goal": goal}, depends_on=[1]),
                PlanStep(3, "Verify execution result and report to Sir", "system", "verify_result",
                         {"goal": goal}, depends_on=[2]),
            ]

        plan = Plan(plan_id=plan_id, goal=goal, target=target, steps=steps)
        event_bus.publish("PLAN_CREATED", {"plan_id": plan_id, "goal": goal, "step_count": len(steps)})
        return plan

    # ── Plan Execution ────────────────────────────────────────────────────────

    def execute_plan(
        self,
        plan: Plan,
        update_callback: Optional[Callable[[PlanStep], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        confirmation_callback: Optional[Callable[[PlanStep], bool]] = None,
    ) -> Tuple[bool, str]:
        """
        Execute a Plan with:
          - Dependency-aware ordering (topological sort)
          - Real dispatch via task_dispatcher
          - Bounded retry (max 2 retries per step on transient failures)
          - Cancellation via cancel_event.set()
          - PRIVILEGED/CRITICAL confirmation gate
          - Honest success/failure — never marks complete when steps failed

        Returns (success: bool, summary_message: str)
        """
        from core.task_dispatcher import task_dispatcher

        if not plan.steps:
            plan.status = "FAILED"
            return False, "Plan contains no executable steps."
        try:
            ordered_steps = self._topological_sort(plan.steps)
        except ValueError as exc:
            plan.status = "FAILED"
            return False, f"Plan validation failed: {exc}"

        effective_cancel_event = cancel_event or threading.Event()

        # Duplicate concurrent execution guard
        with self._running_lock:
            if plan.plan_id in self._running_plans:
                return False, f"Plan {plan.plan_id} is already executing. Duplicate run prevented."
            self._running_plans.add(plan.plan_id)
            self._plan_cancel_events[plan.plan_id] = effective_cancel_event

        task_rec = None
        start_t = time.monotonic()
        verified_ids: Set[int] = set()
        all_files: List[str] = []

        try:
            task_rec = task_center.queue_task(
                goal=plan.goal,
                plan=[s.description for s in plan.steps],
            )
            task_center.register_cancel_event(task_rec.task_id, effective_cancel_event)
            task_center.set_task_running(task_rec.task_id, 0)
            plan.status = "RUNNING"
            event_bus.publish("TASK_STARTED", {"task_id": task_rec.task_id, "goal": plan.goal})

            for step in ordered_steps:
                # Cancellation check
                if effective_cancel_event.is_set():
                    step.status = "CANCELLED"
                    plan.status = "CANCELLED"
                    task_center.cancel_task(task_rec.task_id)
                    if update_callback:
                        update_callback(step)
                    return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."

                # Dependency check — all depends_on must be VERIFIED
                unmet = [d for d in step.depends_on if d not in verified_ids]
                if unmet:
                    step.status = "SKIPPED"
                    step.error_message = f"Blocked: dependencies {unmet} not verified."
                    if update_callback:
                        update_callback(step)
                    continue

                if task_center.requires_confirmation(step.risk_level):
                    if confirmation_callback is None:
                        step.status = "FAILED"
                        step.error_message = "Explicit human confirmation is required, but no approval callback is available."
                        plan.status = "FAILED"
                        task_center.fail_task(task_rec.task_id, step.error_message)
                        if update_callback:
                            update_callback(step)
                        return False, f"{OWNER_ADDRESS}, step '{step.description}' needs explicit approval before execution."
                    if not confirmation_callback(step):
                        step.status = "FAILED"
                        step.error_message = "Explicit human confirmation was denied."
                        plan.status = "FAILED"
                        task_center.fail_task(task_rec.task_id, step.error_message)
                        if update_callback:
                            update_callback(step)
                        return False, f"{OWNER_ADDRESS}, permission for step '{step.description}' was not approved."

                if effective_cancel_event.is_set():
                    step.status = "CANCELLED"
                    plan.status = "CANCELLED"
                    task_center.cancel_task(task_rec.task_id)
                    return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."

                # Execute with bounded retry
                step.status = "EXECUTING"
                task_center.update_task_progress(task_rec.task_id, step.step_id, tool_called=step.action_name)
                if update_callback:
                    update_callback(step)

                dispatch_params = dict(step.params)
                if step.action_name == "verify_result" and not dispatch_params.get("files") and all_files:
                    dispatch_params["files"] = list(all_files)
                result = self._execute_step_with_retry(
                    step, task_dispatcher, effective_cancel_event, params=dispatch_params
                )

                step.result_details = result.output[:500]
                step.generated_files = result.generated_files
                all_files.extend(result.generated_files)

                if effective_cancel_event.is_set() or result.error == "CANCELLED":
                    step.status = "CANCELLED"
                    plan.status = "CANCELLED"
                    task_center.cancel_task(task_rec.task_id)
                    if update_callback:
                        update_callback(step)
                    return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."

                if result.success and result.verified:
                    step.status = "VERIFIED"
                    verified_ids.add(step.step_id)
                    task_center.update_task_progress(
                        task_rec.task_id, step.step_id,
                        tool_called=step.action_name,
                        generated_file=result.generated_files[0] if result.generated_files else "",
                    )
                else:
                    step.status = "FAILED"
                    step.error_message = result.error or result.output[:200]
                    plan.status = "FAILED"
                    task_center.fail_task(task_rec.task_id, step.error_message)
                    if update_callback:
                        update_callback(step)
                    return False, (
                        f"{OWNER_ADDRESS}, step '{step.description}' fail ho gaya: {step.error_message}"
                    )

                if update_callback:
                    update_callback(step)

            unverified_steps = [step for step in plan.steps if step.status != "VERIFIED"]
            if unverified_steps:
                step_ids = [step.step_id for step in unverified_steps]
                plan.status = "FAILED"
                message = f"Required steps were not verified: {step_ids}."
                task_center.fail_task(task_rec.task_id, message)
                return False, message

            if effective_cancel_event.is_set():
                plan.status = "CANCELLED"
                task_center.cancel_task(task_rec.task_id)
                return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."

            duration = round(time.monotonic() - start_t, 2)
            summary = f"All {len(plan.steps)} required steps verified in {duration}s."
            if all_files:
                summary += f" Generated files: {', '.join(all_files[:3])}"

            task_center.complete_task(
                task_rec.task_id,
                result=summary,
                verification="All required PlanSteps marked VERIFIED with handler evidence.",
                generated_files=all_files,
            )
            task_state = task_center.get_task(task_rec.task_id)
            with self._running_lock:
                cancelled = (
                    effective_cancel_event.is_set()
                    or not task_state
                    or task_state.status == TaskStatus.CANCELLED
                )
                task_completed = bool(task_state and task_state.status == TaskStatus.COMPLETED)
                if cancelled:
                    plan.status = "CANCELLED"
                elif not task_completed:
                    plan.status = "FAILED"
                else:
                    plan.status = "COMPLETED"
                    self._running_plans.discard(plan.plan_id)
                    self._plan_cancel_events.pop(plan.plan_id, None)
            if cancelled:
                task_center.cancel_task(task_rec.task_id)
                return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."
            if not task_completed:
                return False, "Task Center did not confirm completion; plan remains failed and unverified."

            timeline.record("PLANNER", f"Plan Completed: {plan.goal}", summary)
            event_bus.publish("TASK_COMPLETED", {"task_id": task_rec.task_id, "duration": duration})

            return True, f"{OWNER_ADDRESS}, goal '{plan.goal}' ke sabhi {len(plan.steps)} steps successfully verify aur complete ho gaye. {summary}"

        except Exception as exc:
            if effective_cancel_event.is_set():
                plan.status = "CANCELLED"
                if task_rec:
                    task_center.cancel_task(task_rec.task_id)
                return False, f"{OWNER_ADDRESS}, plan '{plan.goal}' cancel kar diya gaya hai."
            plan.status = "FAILED"
            if task_rec:
                task_center.fail_task(task_rec.task_id, str(exc))
            return False, f"{OWNER_ADDRESS}, plan execution mein unexpected error: {exc}"

        finally:
            if task_rec:
                task_center.unregister_cancel_event(task_rec.task_id, effective_cancel_event)
            with self._running_lock:
                self._running_plans.discard(plan.plan_id)
                self._plan_cancel_events.pop(plan.plan_id, None)

    def _execute_step_with_retry(
        self,
        step: PlanStep,
        dispatcher,
        cancel_event: Optional[threading.Event],
        params: Optional[Dict[str, Any]] = None,
    ):
        """Execute a step with bounded retry. Returns final DispatchResult."""
        from core.task_dispatcher import DispatchResult

        last_result = DispatchResult(success=False, output="", error="Not started")
        for attempt in range(MAX_RETRIES + 1):
            if cancel_event and cancel_event.is_set():
                return DispatchResult(success=False, output="Cancelled", error="CANCELLED")
            if attempt > 0:
                step.retry_count = attempt
                step.status = "RETRIED"
                if cancel_event and cancel_event.wait(0.5 * attempt):
                    return DispatchResult(success=False, output="Cancelled", error="CANCELLED")
                if not cancel_event:
                    time.sleep(0.5 * attempt)

            last_result = dispatcher.dispatch(
                skill_name=step.skill_name,
                action_name=step.action_name,
                params=step.params if params is None else params,
            )

            if last_result.success and last_result.verified:
                return last_result

            # Don't retry unregistered actions — they won't succeed on retry
            if last_result.error and last_result.error.startswith("UNREGISTERED_ACTION"):
                break

        return last_result

    def _topological_sort(self, steps: List[PlanStep]) -> List[PlanStep]:
        """
        Return dependency-safe order, rejecting malformed or cyclic plans.
        """
        id_map = {s.step_id: s for s in steps}
        if len(id_map) != len(steps):
            raise ValueError("Step IDs must be unique.")
        known_ids = set(id_map)
        missing_ids = sorted({dep for step in steps for dep in step.depends_on if dep not in known_ids})
        if missing_ids:
            raise ValueError(f"Unknown dependency IDs: {missing_ids}.")

        in_degree = {s.step_id: 0 for s in steps}
        for s in steps:
            for dep in s.depends_on:
                in_degree[s.step_id] += 1

        queue = [s for s in steps if in_degree[s.step_id] == 0]
        result = []

        while queue:
            # Use stable sort by step_id within same in-degree level
            queue.sort(key=lambda s: s.step_id)
            current = queue.pop(0)
            result.append(current)
            for s in steps:
                if current.step_id in s.depends_on:
                    in_degree[s.step_id] -= 1
                    if in_degree[s.step_id] == 0:
                        queue.append(s)

        if len(result) != len(steps):
            cyclic_ids = sorted(step_id for step_id, degree in in_degree.items() if degree > 0)
            raise ValueError(f"Dependency cycle detected among step IDs: {cyclic_ids}.")
        return result

    # ── Cancel Running Plan ───────────────────────────────────────────────────

    def cancel_plan(self, plan_id: str) -> bool:
        """Signal cancellation for a running plan; the executor checks between steps."""
        with self._running_lock:
            cancel_event = self._plan_cancel_events.get(plan_id)
            if not cancel_event:
                return False
            cancel_event.set()
            return True


planner_engine = PlannerEngine.get_instance()
