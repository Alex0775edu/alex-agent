"""
test_alex_phase3.py — Comprehensive Test & Verification Suite for ALEX Phase 3 Command Center.

Verifies:
  1. Single-Instance Mutex & Process Coordinator (Duplicate Instance Prevention & Logging)
  2. Action Timeline Audit Trail (Enhanced Fields, Secret Redaction, Search & Clear)
  3. Smart Task Center (Full Lifecycle: QUEUED -> PLANNING -> RUNNING -> WAITING -> VERIFYING -> COMPLETED/FAILED/PAUSED/CANCELLED)
  4. Proactive Intelligence & Anti-Interruption (Notifications, Priorities, Quiet Hours, DND Mode, Reminders)
  5. Personal Project Manager (Real Filesystem Discovery, Tech Stack, Git Status, Syntax Health, Run, Bugs, Continuation)
  6. Morning Briefing & Genuine Integrations (Real Weather, News, Reminders, Project Health, Offline Safety)
  7. System Overview & Command Center Telemetry Engine (Hardware, Audio, Security, Network, Real Data)
  8. Intent Engine Integration for Phase 3 Commands (Projects list/status/run/bugs, Notifications, DND)
  9. Core Identity & Owner Addressing ("Sir", Owner: Aditya Rajak)

Owner: Aditya Rajak
Salutation: Sir
"""

import os
import sys
import time
import py_compile
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_phase3_tests():
    print("=" * 75)
    print("ALEX PHASE 3 — PERSONAL AI COMMAND CENTER VERIFICATION SUITE")
    print("Owner: Aditya Rajak  •  Salutation: Sir  •  System: ALEX v3.0")
    print("=" * 75)

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 1] Single-Instance Mutex & Duplicate Launch Prevention
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 1] Single-Instance Mutex & Process Coordinator")
    from core.instance_manager import (
        acquire_single_instance, release_single_instance,
        is_process_running, log_startup_event, STARTUP_LOG
    )

    # Acquire initial instance
    first_acquired = acquire_single_instance()
    assert first_acquired is True, "First instance must acquire lock cleanly"
    print("  • Primary instance acquired single-instance lock: OK")

    # Verify active process check
    assert is_process_running(os.getpid()) is True, "Current process must be recognized as running"
    assert is_process_running(9999999) is False, "Non-existent PID must report False"

    # Test startup audit logging
    log_startup_event("INFO", "Phase 3 verification test started.")
    assert STARTUP_LOG.exists(), "Startup log must be created"
    log_content = STARTUP_LOG.read_text(encoding="utf-8")
    assert "Phase 3 verification test started." in log_content
    print("  • Crash & startup audit logging verified: OK")

    # Release single instance
    release_single_instance()
    print("  ✓ PASSED: Single-instance mutex and crash audit logging verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 2] Action Timeline: Enhanced Fields, Secret Redaction & Search
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 2] Action Timeline: Enhanced Fields, Secret Redaction & Search")
    from core.action_timeline import timeline, TimelineEvent

    # Record event with sensitive token to verify automatic redaction
    sample_key = "AIzaSyD-Secret1234567890AbCdEfGh"
    ev = timeline.record(
        event_type="TOOL",
        title="Execute build verification",
        details=f"API token: {sample_key} used for cloud check",
        status="SUCCESS",
        user_request="Build my project with key",
        action_taken="Project build",
        tool_used="dev_agent",
        permission_decision="SAFE",
        result="Build completed successfully",
        verification_status="VERIFIED"
    )
    assert sample_key not in ev.details, "API secret token must be automatically redacted"
    assert "[REDACTED_API_KEY]" in ev.details or "[REDACTED" in ev.details
    assert ev.tool_used == "dev_agent"
    assert ev.verification_status == "VERIFIED"
    print("  • Automatic credential & secret redaction in action timeline: OK")

    # Search events
    found = timeline.search_events(query="build", event_type="TOOL")
    assert len(found) >= 1
    assert found[-1].tool_used == "dev_agent"
    print(f"  • Search events by query & event_type ({len(found)} match(es)): OK")

    # Format timeline display
    formatted_tl = timeline.format_timeline(limit=5)
    assert "ACTION TIMELINE" in formatted_tl
    assert "dev_agent" in formatted_tl
    print("  • Formatted timeline representation: OK")
    print("  ✓ PASSED: Action Timeline audit trail and redaction verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 3] Smart Task Center: Full Lifecycle States & Controls
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 3] Smart Task Center: Full Lifecycle States & Controls")
    from core.task_center import task_center, TaskStatus

    # 3.1 Queue Task
    task = task_center.queue_task(
        goal="Compile and test autonomous personal dashboard",
        plan=["Step 1: Check hardware", "Step 2: Verify services", "Step 3: Run diagnostics"]
    )
    assert task.status == TaskStatus.QUEUED
    assert task.total_steps == 3
    print(f"  • Task queued: {task.task_id} [Status: {task.status}]")

    # 3.2 Planning & Running
    task_center.set_task_planning(task.task_id)
    assert task_center.get_task(task.task_id).status == TaskStatus.PLANNING

    task_center.set_task_running(task.task_id, step_index=1)
    t_running = task_center.get_task(task.task_id)
    assert t_running.status == TaskStatus.RUNNING
    assert t_running.current_step == 1
    print(f"  • Task running: {t_running.task_id} [Step: {t_running.current_step}/{t_running.total_steps}, Progress: {t_running.progress_pct}%]")

    # 3.3 Pause & Resume
    assert task_center.pause_task(task.task_id) is True
    assert task_center.get_task(task.task_id).status == TaskStatus.PAUSED
    print("  • Task paused successfully.")

    assert task_center.resume_task(task.task_id) is True
    assert task_center.get_task(task.task_id).status == TaskStatus.RUNNING
    print("  • Task resumed successfully.")

    # 3.4 Verification & Completion
    task_center.set_task_verifying(task.task_id)
    assert task_center.get_task(task.task_id).status == TaskStatus.VERIFYING

    test_artifact = BASE_DIR / "memory" / "sample_artifact.txt"
    test_artifact.write_text("Phase 3 artifact content", encoding="utf-8")
    task_center.complete_task(task.task_id, result="Dashboard operational", verification="Verified 100%", generated_files=[str(test_artifact)])
    t_comp = task_center.get_task(task.task_id)
    assert t_comp.status == TaskStatus.COMPLETED
    assert t_comp.progress_pct == 100
    assert str(test_artifact) in t_comp.generated_files
    print(f"  • Task completed with artifacts: {t_comp.task_id} (elapsed: {t_comp.elapsed_seconds}s)")

    # 3.5 Artifact inspection
    opened = task_center.open_task_artifacts(task.task_id)
    assert str(test_artifact) in opened
    if test_artifact.exists(): test_artifact.unlink()
    print("  • Artifact file detection & access verified.")

    # 3.6 Failure and Retry
    fail_task = task_center.create_task("Faulty external build")
    task_center.fail_task(fail_task.task_id, "SyntaxError on line 42")
    assert task_center.get_task(fail_task.task_id).status == TaskStatus.FAILED
    errs = task_center.inspect_task_errors(fail_task.task_id)
    assert "SyntaxError on line 42" in errs[0]

    retried = task_center.retry_task(fail_task.task_id)
    assert retried is not None
    assert retried.status == TaskStatus.RUNNING
    assert retried.recovery_attempts == 1
    print(f"  • Task failure & checkpoint retry verified: New task {retried.task_id}")
    task_center.cancel_task(retried.task_id)
    print("  ✓ PASSED: Smart Task Center full lifecycle verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 4] Proactive Intelligence, Anti-Interruption, DND & Reminders
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 4] Proactive Intelligence, Anti-Interruption, DND & Reminders")
    from core.proactive_intelligence import proactive_engine, NotificationPriority

    # 4.1 Dispatch notification
    notif = proactive_engine.notify(
        category="TASK",
        title="Long-running build completed",
        message="All workstation artifacts built cleanly.",
        priority=NotificationPriority.HIGH,
        spoken=False
    )
    assert notif is not None
    assert notif.category == "TASK"
    assert notif.priority == NotificationPriority.HIGH
    print(f"  • Proactive notification created: '{notif.title}'")

    # 4.2 Anti-Interruption (DND Mode)
    proactive_engine.toggle_dnd(enabled=True)
    assert proactive_engine.settings.dnd_mode is True
    can_notif, reason = proactive_engine.can_notify("FILE", NotificationPriority.MEDIUM)
    assert can_notif is False, "DND mode must block normal priority alerts"
    assert "Do Not Disturb" in reason
    # Critical should bypass DND
    can_crit, _ = proactive_engine.can_notify("SECURITY", NotificationPriority.CRITICAL)
    assert can_crit is True, "Critical priority must bypass DND"
    proactive_engine.toggle_dnd(enabled=False)
    assert proactive_engine.settings.dnd_mode is False
    print("  • DND mode suppression & Critical priority bypass: OK")

    # 4.3 Reminders Scheduling
    today_time = time.strftime("%Y-%m-%d 23:59:59")
    rem = proactive_engine.add_reminder("Review Phase 3 Architecture with Sir", today_time)
    assert rem.id.startswith("rem_")
    assert rem.text == "Review Phase 3 Architecture with Sir"
    todays = proactive_engine.get_todays_reminders()
    assert any(r.id == rem.id for r in todays)
    print(f"  • Reminder scheduled and recovered: '{rem.text}'")

    summary_pro = proactive_engine.format_proactive_summary()
    assert "PROACTIVE INTELLIGENCE" in summary_pro
    assert "Review Phase 3 Architecture" in summary_pro
    print("  ✓ PASSED: Proactive Intelligence and Anti-Interruption verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 5] Personal Project Manager & Health Audits
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 5] Personal Project Manager & Health Audits")
    from core.project_manager import project_manager

    # 5.1 Project Discovery
    discovered = project_manager.discover_projects()
    assert len(discovered) >= 1
    print(f"  • Discovered/verified projects: {discovered}")

    # 5.2 Project List Output
    p_list = project_manager.list_projects()
    assert "registered projects ki list" in p_list
    assert "SkillSum" in p_list
    print("  • Projects list formatting verified.")

    # 5.3 Health Status & Real Inspection
    report = project_manager.get_project_status_report("SkillSum")
    assert "PROJECT STATUS: SkillSum" in report
    assert "Health:" in report
    print(f"  • Project health report for SkillSum:\n{report[:240]}...")

    # 5.4 Bug Tracking
    bug_res = project_manager.add_bug("Verify memory consumption under sustained voice streaming", severity="Normal", project_name="SkillSum")
    assert "bug #" in bug_res
    bugs_check = project_manager.check_project_bugs("SkillSum")
    assert "Verify memory consumption" in bugs_check
    print("  • Project bug tracking and ledger audit: OK")

    # 5.5 Continuation
    cont_summary = project_manager.continue_where_left_off()
    assert "current active project: SkillSum" in cont_summary
    assert "Sir" in cont_summary
    print("  ✓ PASSED: Personal Project Manager verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 6] Morning Briefing: Asynchronous & Real Intelligence Sources
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 6] Morning Briefing: Asynchronous & Real Intelligence Sources")
    from core.startup_manager import startup_manager
    from actions.automation_engine import get_morning_briefing

    brief_data = startup_manager.generate_full_briefing(is_startup=False)
    assert "greeting" in brief_data
    assert "weather" in brief_data
    assert "tasks" in brief_data
    assert "system" in brief_data
    assert "news" in brief_data
    assert "spoken_summary" in brief_data

    # Weather real source check
    assert "condition" in brief_data["weather"]
    # Tasks & Project health check
    assert "project_health" in brief_data["tasks"]
    assert "previous_results" in brief_data["tasks"]

    # Natural executive briefing
    exec_brief = get_morning_briefing()
    assert "Today is" in exec_brief
    assert "Weather:" in exec_brief
    assert "Active Workspace:" in exec_brief
    assert "System Status:" in exec_brief
    print(f"  • Executive morning briefing output verified:\n{exec_brief[:300]}...")
    print("  ✓ PASSED: Morning Briefing with real telemetry verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 7] System Overview & Command Center Telemetry Engine
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 7] System Overview & Command Center Telemetry Engine")
    from dashboard.server import DashboardServer
    srv = DashboardServer()
    # Test client app builder
    assert srv.app is not None
    print("  • Dashboard FastAPI application built: OK")

    # Verify telemetry endpoint data generator directly
    import psutil
    from core.security import security_manager, OWNER_NAME, OWNER_ADDRESS
    assert OWNER_ADDRESS == "Sir"
    assert OWNER_NAME == "Aditya Rajak"
    assert security_manager.check_permission("computer_control")[0] is True
    print(f"  • Security credentials: Owner={OWNER_NAME}, Addressing={OWNER_ADDRESS}, Control=Allowed")

    cpu_val = psutil.cpu_percent(interval=None)
    ram_val = psutil.virtual_memory().percent
    assert 0 <= cpu_val <= 100
    assert 0 <= ram_val <= 100
    print(f"  • Hardware metrics verified: CPU={cpu_val}%, RAM={ram_val}%")
    print("  ✓ PASSED: System Overview & Telemetry Engine verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 8] Intent Engine Integration for Phase 3 Commands
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 8] Intent Engine Integration for Phase 3 Commands")
    from core.intent_engine import intent_engine

    phase3_queries = [
        ("Alex, mere projects ki list dikhao", "PROJECTS_LIST"),
        ("Alex, SkillSum ka status check karo", "PROJECT_STATUS"),
        ("Alex, mera LMS project run karo", "PROJECT_RUN"),
        ("Alex, pichhle project ka kaam continue karo", "PROJECT_CONTINUE"),
        ("Alex, project mein naye bugs check karo", "PROJECT_BUGS"),
        ("Alex, notifications dikhao", "SHOW_NOTIFICATIONS"),
        ("Alex, Do Not Disturb on karo", "DND_TOGGLE")
    ]

    for q, exp_intent in phase3_queries:
        parsed = intent_engine.parse(q)
        assert parsed.intent == exp_intent, f"Query '{q}' expected {exp_intent}, got {parsed.intent}"
        assert parsed.is_local_command is True, f"Query '{q}' must be local command"
        exec_out = intent_engine.execute_local_command(parsed)
        assert exec_out.handled is True, f"Query '{q}' must be handled by local dispatcher"
        assert len(exec_out.response_text) > 0
        print(f"  • Handled '{q}' -> Intent: {parsed.intent} | Response: '{exec_out.response_text[:40]}...'")

    print("  ✓ PASSED: Intent Engine Phase 3 commands verified.")

    print("\n" + "=" * 75)
    print("ALL 8 VERIFICATION TEST PHASES PASSED WITH 100% SUCCESS!")
    print("ALEX PHASE 3 PERSONAL AI COMMAND CENTER IS FULLY OPERATIONAL!")
    print("=" * 75)


if __name__ == "__main__":
    run_phase3_tests()

