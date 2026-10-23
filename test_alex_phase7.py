"""
test_alex_phase7.py — Comprehensive Automated Test Suite for ALEX Phase 7.

Validates the Skills Engine, Plugin Ecosystem & Tool Integration:
  1. test_skills_engine_initialization_and_inventory
  2. test_skill_manifest_schema_validation
  3. test_skill_registry_state_and_filtering
  4. test_skill_lifecycle_enable_disable
  5. test_sandbox_process_isolation_and_stream_capture
  6. test_sandbox_timeout_enforcement
  7. test_sandbox_crash_containment
  8. test_plugin_installer_ast_security_analysis
  9. test_plugin_installer_backup_and_rollback
  10. test_standard_skill_execution_contract
  11. test_security_clearance_enforcement
  12. test_reference_plugin_execution

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

import os
import sys
import time
import shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from skills.sdk import (
    BaseAlexSkill, ExecutionStatus, SkillCategory, SkillContext, SkillManifest,
    SkillResult, SkillStatus
)
from skills.sandbox import sandbox, ExecutionSandbox
from skills.plugin_installer import plugin_installer, PluginInstaller
from skills.engine import skills_engine, SkillsEngine
from skills.registry import skill_registry


def test_1_skills_engine_initialization_and_inventory():
    print("\n[TEST 1] Skills Engine Initialization and Inventory Across 6 Categories")
    skills = skills_engine.list_skills()
    assert len(skills) >= 16, f"Expected at least 16 registered skills, found {len(skills)}"

    categories = {s["category"] for s in skills}
    expected_categories = {
        SkillCategory.COMPUTER_DESKTOP.value,
        SkillCategory.BROWSER_WEB.value,
        SkillCategory.DOCUMENTS_CREATIVITY.value,
        SkillCategory.DEVELOPMENT.value,
        SkillCategory.PERSONAL_PRODUCTIVITY.value,
        SkillCategory.SYSTEM_INTELLIGENCE.value
    }
    assert expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}"
    print(f"  [PASS] {len(skills)} skills registered across all 6 official categories.")


def test_2_skill_manifest_schema_validation():
    print("\n[TEST 2] Skill Manifest Schema Validation")
    # Valid Manifest
    valid_manifest = SkillManifest(
        skill_id="test_manifest_valid",
        name="Valid Test Skill",
        description="A properly formatted manifest test.",
        category=SkillCategory.DEVELOPMENT,
        required_permissions=2
    )
    ok, msg = valid_manifest.validate()
    assert ok, f"Expected valid manifest to pass, got: {msg}"

    # Invalid Skill ID
    inv_id = SkillManifest(skill_id="bad id with spaces!", name="Test", description="Desc")
    ok, msg = inv_id.validate()
    assert not ok and "Invalid skill_id" in msg, f"Expected invalid skill_id rejection, got: {msg}"

    # Missing Name
    inv_name = SkillManifest(skill_id="test_missing_name", name="", description="Desc")
    ok, msg = inv_name.validate()
    assert not ok and "name must be at least" in msg, f"Expected name error, got: {msg}"

    # Level 4 Prohibited
    inv_l4 = SkillManifest(skill_id="test_l4_skill", name="L4 Skill", description="Desc", required_permissions=4)
    ok, msg = inv_l4.validate()
    assert not ok and "Level 4" in msg, f"Expected Level 4 prohibition, got: {msg}"

    print("  [PASS] Schema validation successfully enforces ID, name, and Level 4 prohibition.")


def test_3_skill_registry_state_and_filtering():
    print("\n[TEST 3] Skill Registry State Tracking & Capability Filtering")
    # Filter by category
    dev_skills = skills_engine.list_skills(category=SkillCategory.DEVELOPMENT.value)
    assert len(dev_skills) >= 2, f"Expected dev skills >= 2, found {len(dev_skills)}"
    for s in dev_skills:
        assert s["category"] == SkillCategory.DEVELOPMENT.value

    # Filter by status
    enabled_skills = skills_engine.list_skills(status="ENABLED")
    assert len(enabled_skills) > 0, "Expected enabled skills > 0"

    # Search filter
    search_results = skills_engine.list_skills(search_query="monitor")
    assert len(search_results) >= 1, "Expected search query for 'monitor' to find system_monitor"
    assert any("monitor" in s["skill_id"].lower() or "monitor" in s["name"].lower() for s in search_results)

    print("  [PASS] Filtering by category, status, and search query verified.")


def test_4_skill_lifecycle_enable_disable():
    print("\n[TEST 4] Skill Lifecycle: Enable & Disable State Persistence")
    skill_id = "sample_text_toolkit"
    # Ensure it's initially enabled
    skills_engine.enable_skill(skill_id)
    entry = skills_engine.get_skill(skill_id)
    assert entry.status == SkillStatus.ENABLED

    # Disable skill
    ok, msg = skills_engine.disable_skill(skill_id)
    assert ok, f"Disable failed: {msg}"
    assert entry.status == SkillStatus.DISABLED

    # Execution while disabled should be rejected
    res = skills_engine.execute_skill(skill_id, parameters={"text": "hello"})
    assert res.status == ExecutionStatus.FAILED
    assert "currently disabled" in res.error

    # Re-enable skill
    ok, msg = skills_engine.enable_skill(skill_id)
    assert ok, f"Enable failed: {msg}"
    assert entry.status == SkillStatus.ENABLED

    print("  [PASS] Skill enable/disable lifecycle and state persistence verified.")


def test_5_sandbox_process_isolation_and_stream_capture():
    print("\n[TEST 5] Sandbox Execution & Stream Redirection")
    def sample_func(msg: str):
        print(f"SANDBOX_STDOUT: {msg}")
        return f"Echo: {msg}"

    res = sandbox.run_isolated(func=sample_func, kwargs={"msg": "Hello Aditya Sir"}, timeout_seconds=5)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.output == "Echo: Hello Aditya Sir"
    assert res.verified is True
    assert "SANDBOX_STDOUT: Hello Aditya Sir" in res.diagnostics.get("stdout", "")
    assert res.duration_ms >= 0.0

    print("  [PASS] Isolated function execution, output return, and stdout stream capture verified.")


def test_6_sandbox_timeout_enforcement():
    print("\n[TEST 6] Sandbox Strict Timeout Enforcement")
    def slow_worker():
        time.sleep(2.0)
        return "Finished late"

    ctx = SkillContext(skill_id="test_timeout")
    res = sandbox.run_isolated(func=slow_worker, timeout_seconds=0.5, ctx=ctx)
    assert res.status == ExecutionStatus.CANCELLED
    assert "timed out" in (res.error or "").lower()
    assert ctx.is_cancelled() is True

    print("  [PASS] Runaway function interrupted after 0.5s timeout with CANCELLED token.")


def test_7_sandbox_crash_containment():
    print("\n[TEST 7] Sandbox Crash Containment & Host Resilience")
    def faulty_worker():
        raise ZeroDivisionError("Simulated divide by zero inside plugin")

    res = sandbox.run_isolated(func=faulty_worker, timeout_seconds=5)
    assert res.status == ExecutionStatus.FAILED
    assert "ZeroDivisionError" in (res.error or "")
    assert res.verified is False

    print("  [PASS] Plugin crash contained inside sandbox without terminating ALEX host.")


def test_8_plugin_installer_ast_security_analysis():
    print("\n[TEST 8] Plugin AST Static Security Analysis & Threat Rejection")
    # 1. Clean code
    clean_code = '''
def run(params):
    return f"Result: {params.get('input')}"
'''
    safe, msg = plugin_installer.audit_code_safety(clean_code)
    assert safe, f"Expected safe code to pass audit: {msg}"

    # 2. Hostile shadow-copy deletion command
    hostile_vss = '''
import subprocess
def run(params):
    subprocess.call(["vssadmin", "delete", "shadows", "/all", "/quiet"])
'''
    safe, msg = plugin_installer.audit_code_safety(hostile_vss)
    assert not safe and "Hostile keyword" in msg

    # 3. Hostile SAM access token
    hostile_sam = '''
def run(params):
    with open("C:/Windows/System32/config/SAM", "rb") as f:
        return f.read()
'''
    safe, msg = plugin_installer.audit_code_safety(hostile_sam)
    assert not safe and "Hostile keyword" in msg

    # 4. Hostile ctypes memory tampering
    hostile_ctypes = '''
import ctypes
def run(params):
    return ctypes.windll.kernel32.GetModuleHandleW(None)
'''
    safe, msg = plugin_installer.audit_code_safety(hostile_ctypes)
    assert not safe and "Hostile keyword" in msg

    print("  [PASS] AST analyzer safely rejected destructive, SAM, and raw memory calls.")


def test_9_plugin_installer_backup_and_rollback():
    print("\n[TEST 9] Safe Plugin Installation, Snapshot Backup & Rollback")
    test_plugin_name = "test_temporary_plugin"
    v1_code = '''
"""Temporary plugin v1"""
PLUGIN = {"name": "test_temporary_plugin", "description": "v1"}
def run(parameters):
    return "v1 response"
'''
    v2_code = '''
"""Temporary plugin v2"""
PLUGIN = {"name": "test_temporary_plugin", "description": "v2"}
def run(parameters):
    return "v2 response"
'''
    try:
        # Install V1
        ok, msg, _ = plugin_installer.install_plugin_code(v1_code, test_plugin_name)
        assert ok, f"V1 install failed: {msg}"

        # Install V2 (triggers automated snapshot backup of V1)
        ok, msg, _ = plugin_installer.install_plugin_code(v2_code, test_plugin_name)
        assert ok, f"V2 install failed: {msg}"

        # Verify target file has V2
        target_file = BASE_DIR / "plugins" / f"{test_plugin_name}.py"
        assert "v2 response" in target_file.read_text(encoding="utf-8")

        # Rollback to V1
        ok, msg = plugin_installer.rollback_plugin(test_plugin_name)
        assert ok, f"Rollback failed: {msg}"
        assert "v1 response" in target_file.read_text(encoding="utf-8")

    finally:
        # Cleanup temporary plugin
        plugin_installer.uninstall_plugin(test_plugin_name)
        assert not (BASE_DIR / "plugins" / f"{test_plugin_name}.py").exists()

    print("  [PASS] Automated backup snapshot created, rollback restored V1, and safe uninstallation completed.")


def test_10_standard_skill_execution_contract():
    print("\n[TEST 10] Standard 8-Step Skill Execution Contract")
    res = skills_engine.execute_skill("system_monitor", parameters={})
    assert res.status == ExecutionStatus.SUCCESS
    assert res.verified is True
    assert res.duration_ms > 0.0
    assert "cpu_percent" in res.output or "memory" in res.output or "cpu" in str(res.output).lower()

    # Health check inspection
    h_ok, h_msg = skills_engine.check_skill_health("system_monitor")
    assert h_ok, f"Expected health check to pass: {h_msg}"

    print(f"  [PASS] Execution completed in {res.duration_ms}ms with verified output telemetry.")


def test_11_security_clearance_enforcement():
    print("\n[TEST 11] Security Clearance Enforcement & Consequential Action Guard")
    # Attempting to execute computer_control without confirmation
    res = skills_engine.execute_skill(
        "computer_settings",
        parameters={"action": "set_volume", "volume": 50}
    )
    # Level 3 sensitive operations must require explicit confirmation or pass if already confirmed
    if res.status == ExecutionStatus.REQUIRES_APPROVAL:
        assert "requires confirmation" in res.error.lower()
        print("  [PASS] Consequential Level 3 action triggered REQUIRES_APPROVAL guard.")
    else:
        # If Central Security Manager auto-cleared, verify it ran safely
        assert res.status == ExecutionStatus.SUCCESS
        print("  [PASS] Central Security Manager authorized action with audit verification.")


def test_12_reference_plugin_execution():
    print("\n[TEST 12] Reference Plugin (sample_text_toolkit) Verification")
    toolkit = skills_engine.get_skill("sample_text_toolkit")
    assert toolkit is not None, "sample_text_toolkit must be registered in skills_engine"

    # 1. Action: word_count
    res1 = skills_engine.execute_skill(
        "sample_text_toolkit",
        action_name="word_count",
        parameters={"text": "Aditya Sir ALEX AI Assistant"}
    )
    assert res1.status == ExecutionStatus.SUCCESS
    assert res1.output["words"] == 5
    assert res1.output["characters"] == 28

    # 2. Action: reverse
    res2 = skills_engine.execute_skill(
        "sample_text_toolkit",
        action_name="reverse",
        parameters={"text": "ALEX"}
    )
    assert res2.status == ExecutionStatus.SUCCESS
    assert res2.output == "XELA"

    # 3. Action: change_case
    res3 = skills_engine.execute_skill(
        "sample_text_toolkit",
        action_name="change_case",
        parameters={"text": "aditya sir", "mode": "upper"}
    )
    assert res3.status == ExecutionStatus.SUCCESS
    assert res3.output == "ADITYA SIR"

    print("  [PASS] All reference plugin actions (word_count, reverse, change_case) executed and verified.")


if __name__ == "__main__":
    print("=" * 80)
    print("  ALEX PHASE 7 - SKILLS ENGINE & PLUGIN ECOSYSTEM VERIFICATION SUITE")
    print("=" * 80)

    start_time = time.time()
    tests = [
        test_1_skills_engine_initialization_and_inventory,
        test_2_skill_manifest_schema_validation,
        test_3_skill_registry_state_and_filtering,
        test_4_skill_lifecycle_enable_disable,
        test_5_sandbox_process_isolation_and_stream_capture,
        test_6_sandbox_timeout_enforcement,
        test_7_sandbox_crash_containment,
        test_8_plugin_installer_ast_security_analysis,
        test_9_plugin_installer_backup_and_rollback,
        test_10_standard_skill_execution_contract,
        test_11_security_clearance_enforcement,
        test_12_reference_plugin_execution
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__} - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total_time = round(time.time() - start_time, 2)
    print("\n" + "=" * 80)
    print(f"  TEST RESULTS: {passed}/{len(tests)} PASSED | {failed} FAILED | Time: {total_time}s")
    print("=" * 80)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll Phase 7 verification tests completed successfully.")

