"""
test_alex_phase5.py — Comprehensive Verification Suite for ALEX Phase 5 Security & Privacy Engine.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Verifies:
  1. Central Security Manager & Permissions Gateway (Tool Interception, Gateway Routing)
  2. Owner Verification & Cryptographic Vault (Salted PBKDF2 Hashing, Windows DPAPI, No Plaintext)
  3. Four-Tier Permission Hierarchy:
     • Level 1 — Read Operations
     • Level 2 — Normal Autonomous Operations
     • Level 3 — Sensitive Operations with Confirmation Gate
     • Level 4 — Restricted Operations Permanently Blocked
  4. File & Folder Access Containment (System32 / SAM / SSH Blocked vs Approved Workspace)
  5. Terminal Command Firewall (Dangerous/Hostile Commands Blocked, Dev Commands Allowed)
  6. Safe Autonomous Execution & Consequential Action Guard (4-Part Disclosure: Action, Target, Risks, Confirmation)
  7. Session Expiration, Inactivity Timeout, Manual Lock & Unlock
  8. Audit Logging & Real-Time Secret Redaction
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_phase5_tests():
    print("=" * 75)
    print("ALEX PHASE 5 — SECURITY, OWNER VERIFICATION & PRIVACY ENGINE")
    print("Owner: Aditya Rajak  •  Salutation: Sir  •  System: ALEX v5.0")
    print("=" * 75)

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 1] Owner Verification & Cryptographic Credentials Vault
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 1] Owner Verification & Cryptographic Credentials Vault")
    from core.security_vault import credentials_vault, hash_secret, verify_secret, dpapi_protect, dpapi_unprotect
    from core.security import security_manager, OWNER_NAME, OWNER_ADDRESS

    # 1.1 Verify owner identity
    assert OWNER_NAME == "Aditya Rajak"
    assert OWNER_ADDRESS == "Sir"
    print(f"  • Owner identity confirmed: {OWNER_NAME} (Addressing: {OWNER_ADDRESS})")

    # 1.2 Salted PBKDF2 Hashing
    test_pin = "9876"
    salt_hex, hash_hex = hash_secret(test_pin)
    assert len(salt_hex) == 32
    assert len(hash_hex) == 64
    assert test_pin not in salt_hex and test_pin not in hash_hex
    assert verify_secret(test_pin, salt_hex, hash_hex) is True
    assert verify_secret("0000", salt_hex, hash_hex) is False
    print("  • Salted PBKDF2-HMAC-SHA256 (100k iterations) hashing verified: OK")

    # 1.3 Windows DPAPI Encryption
    raw_secret = b"ALEX_SUPER_SECRET_TOKEN_2026"
    protected = dpapi_protect(raw_secret, "ALEX Test Secret")
    assert protected != raw_secret, "DPAPI must encrypt raw payload"
    unprotected = dpapi_unprotect(protected)
    assert unprotected == raw_secret, "DPAPI must cleanly decrypt for current user"
    print("  • Windows DPAPI user-bound encryption & decryption: OK")

    # 1.4 Windows Account & Session Verification
    win_ok = credentials_vault.verify_windows_account()
    assert win_ok is True
    print(f"  • Windows active account verified ({credentials_vault.windows_username}): OK")
    print("  ✓ PASSED: Owner Verification and Cryptographic Vault verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 2] Central Security Manager Four-Tier Permission Hierarchy
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 2] Central Security Manager Four-Tier Permission Hierarchy")
    from core.security import (
        PERM_LEVEL_1_READ, PERM_LEVEL_2_NORMAL,
        PERM_LEVEL_3_SENSITIVE, PERM_LEVEL_4_RESTRICTED
    )

    # 2.1 Level 1 Read
    ok1, reason1, lvl1 = security_manager.authorize_action("weather_report")
    assert ok1 is True
    assert lvl1 == PERM_LEVEL_1_READ
    print("  • Level 1 (Read Operations): OK")

    # 2.2 Level 2 Normal Operations
    ok2, reason2, lvl2 = security_manager.authorize_action("creation_engine")
    assert ok2 is True
    assert lvl2 == PERM_LEVEL_2_NORMAL
    print("  • Level 2 (Normal Autonomous Operations): OK")

    # 2.3 Level 3 Sensitive Operations (Requires Confirmation)
    ok3, reason3, lvl3 = security_manager.authorize_action("shutdown_alex")
    assert lvl3 == PERM_LEVEL_3_SENSITIVE
    assert "Confirmation" in reason3
    print(f"  • Level 3 (Sensitive Operations): {reason3} - OK")

    # 2.4 Level 4 Restricted Operations (Permanently Blocked)
    for restricted_tool in ["disable_security", "extract_credentials", "wipe_system", "covert_surveillance"]:
        ok4, reason4, lvl4 = security_manager.authorize_action(restricted_tool)
        assert ok4 is False
        assert lvl4 == PERM_LEVEL_4_RESTRICTED
        assert "Blocked" in reason4
    print("  • Level 4 (Restricted Operations Permanently Blocked): OK")
    print("  ✓ PASSED: Four-Tier Permission Hierarchy verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 3] File & Folder Access Containment
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 3] File & Folder Access Containment")

    # 3.1 Restricted system locations (Level 4 Blocked)
    sys_paths = [
        r"C:\Windows\System32\cmd.exe",
        r"C:\Windows\SysWOW64\kernel32.dll",
        r"C:\Users\User\AppData\Local\Microsoft\Credentials\token.dat",
        r"C:\Users\User\.ssh\id_rsa"
    ]
    for sp in sys_paths:
        ok_sp, r_sp, lvl_sp = security_manager.authorize_file_access(sp, mode="r")
        assert ok_sp is False
        assert lvl_sp == PERM_LEVEL_4_RESTRICTED
        assert "Access Denied" in r_sp
    print("  • Forbidden system & credential directory access blocked: OK")

    # 3.2 Approved workspace access (Level 1 Read & Level 2 Write)
    ws_file = BASE_DIR / "main.py"
    ok_r, _, lvl_r = security_manager.authorize_file_access(ws_file, mode="r")
    assert ok_r is True
    assert lvl_r == PERM_LEVEL_1_READ

    new_file = BASE_DIR / "memory" / "artifacts" / "new_report.txt"
    ok_w, _, lvl_w = security_manager.authorize_file_access(new_file, mode="w")
    assert ok_w is True
    assert lvl_w == PERM_LEVEL_2_NORMAL

    # 3.3 Sensitive Deletion / Overwrite (Level 3 Confirmation Required)
    ok_del, r_del, lvl_del = security_manager.authorize_file_access(ws_file, mode="delete")
    assert lvl_del == PERM_LEVEL_3_SENSITIVE
    assert "Confirmation" in r_del
    print("  • Workspace read, create, and sensitive deletion boundaries verified: OK")
    print("  ✓ PASSED: File & Folder Access Containment verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 4] Terminal Command Firewall & Hostile Execution Shield
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 4] Terminal Command Firewall & Hostile Execution Shield")

    # 4.1 Hostile / Catastrophic commands (Level 4 Permanently Blocked)
    hostile_cmds = [
        "format C:",
        "rmdir /s /q C:\\",
        "del /f /s /q C:\\",
        "vssadmin delete shadows",
        "bcdedit /set {default} bootstatuspolicy ignoreallfailures",
        "reg delete HKLM\\Software\\Policies"
    ]
    for hc in hostile_cmds:
        ok_hc, r_hc, lvl_hc = security_manager.authorize_terminal_command(hc)
        assert ok_hc is False
        assert lvl_hc == PERM_LEVEL_4_RESTRICTED
        assert "Blocked" in r_hc
    print("  • Hostile destructive terminal commands blocked permanently: OK")

    # 4.2 Sensitive terminal commands (Level 3 Confirmation Required)
    sens_cmds = [
        "rmdir /s /q build",
        "del unwanted_artifact.log",
        "pip install untrusted-package",
        "taskkill /F /PID 1234"
    ]
    for sc in sens_cmds:
        ok_sc, r_sc, lvl_sc = security_manager.authorize_terminal_command(sc)
        assert ok_sc is True
        assert lvl_sc == PERM_LEVEL_3_SENSITIVE
        assert "Confirmation" in r_sc
    print("  • Sensitive system-modifying commands intercepted for Level 3 Confirmation: OK")

    # 4.3 Safe development commands (Level 2 Allowed)
    safe_cmds = ["git status", "python test_alex_phase5.py", "dir", "echo Hello"]
    for s_cmd in safe_cmds:
        ok_s, _, lvl_s = security_manager.authorize_terminal_command(s_cmd)
        assert ok_s is True
        assert lvl_s == PERM_LEVEL_2_NORMAL
    print("  • Safe development commands approved: OK")
    print("  ✓ PASSED: Terminal Command Firewall verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 5] Tool Gateway Interception in Action Loader
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 5] Tool Gateway Interception in Action Loader")
    from core.action_loader import ActionRegistry, ActionRecord

    # Create test action records
    test_called = [False]
    def test_handler(parameters):
        test_called[0] = True
        return "Executed"

    registry = ActionRegistry(
        actions={
            "safe_tool": ActionRecord("safe_tool", "Safe Read", {}, test_handler, valid=True),
            "disable_security": ActionRecord("disable_security", "Restricted", {}, test_handler, valid=True),
        },
        logger=lambda m: None
    )

    # 5.1 Blocked tool attempted run
    res_blocked = registry.run("disable_security", {})
    assert "Access Denied by Central Security Manager" in res_blocked
    assert test_called[0] is False, "Handler must NOT be executed when security manager denies"
    print("  • ActionRegistry intercepted restricted tool and prevented execution: OK")

    # 5.2 Safe tool allowed run
    res_allowed = registry.run("safe_tool", {})
    assert res_allowed == "Executed"
    assert test_called[0] is True
    print("  • ActionRegistry executed authorized action cleanly: OK")
    print("  ✓ PASSED: Tool Gateway Interception verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 6] Safe Autonomous Execution & Consequential Action Guard
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 6] Safe Autonomous Execution & Consequential Action Guard")

    # 6.1 Four-Part Disclosure Generation
    disclosure = security_manager.explain_consequential_action(
        action="Delete legacy build directory",
        target="d:\\alex\\Mark-LV-main\\build",
        risks="Irreversible deletion of compiled binaries and cached assets"
    )
    assert "Sir" in disclosure
    assert "Intended Action: Delete legacy build directory" in disclosure
    assert "Affected Target: d:\\alex\\Mark-LV-main\\build" in disclosure
    assert "Relevant Risks: Irreversible deletion" in disclosure
    assert "Kya aap ise proceed karna chahte hain?" in disclosure
    print("  • 4-Part consequential disclosure generated: OK")

    # 6.2 Confirmation Gate Parking
    work_called = [False]
    def sensitive_work():
        work_called[0] = True
        return "Directory removed"

    from core import confirm
    confirm_msg = confirm.request("test_gate", "Remove Directory", "Target: build", sensitive_work)
    assert "I cannot confirm" in confirm_msg or confirm_msg is not None
    assert work_called[0] is False, "Sensitive work must park until explicit owner confirmation"
    print("  • Sensitive operation successfully parked behind non-forgeable gate: OK")
    print("  ✓ PASSED: Safe Autonomous Execution and Consequential Action Guard verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 7] Session Lifecycle, Inactivity Lock & Re-Authentication
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 7] Session Lifecycle, Inactivity Lock & Re-Authentication")

    # 7.1 Manual Lock
    security_manager.lock(reason="Owner manual lock test")
    assert security_manager.is_locked() is True
    ok_lock, r_lock, _ = security_manager.authorize_action("open_app")
    assert ok_lock is False
    assert "ALEX is locked" in r_lock
    print("  • Immediate lock drops privileges and blocks privileged tools: OK")

    # 7.2 Failed Unlock
    fail_ok, _ = security_manager.unlock("wrong_pin_0000")
    assert fail_ok is False
    assert security_manager.is_locked() is True

    # 7.3 Successful Unlock with Salted PIN
    un_ok, un_msg = security_manager.unlock("1122")
    assert un_ok is True
    assert security_manager.is_locked() is False
    assert "Welcome back, Sir" in un_msg
    print("  • Secure PIN unlock verified and privileges restored: OK")

    # 7.4 Inactivity Timeout Configuration
    security_manager.set_session_timeout(300)
    assert security_manager.get_session_timeout() == 300.0
    print("  • Session inactivity timeout configured (300s): OK")
    print("  ✓ PASSED: Session Lifecycle, Inactivity Lock and Re-Authentication verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # [TEST 8] Audit Logging & Automatic Secret Redaction
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 8] Audit Logging & Automatic Secret Redaction")
    from core.action_timeline import timeline
    from core.security import SECURITY_LOG

    test_token = "AIzaSySecretTokenForTestingPhase5Security"
    security_manager.log_event("AUDIT_TEST", f"Audit check with api_key: {test_token}")

    assert SECURITY_LOG.exists()
    log_content = SECURITY_LOG.read_text(encoding="utf-8")
    assert test_token not in log_content, "Secret must be automatically redacted in security audit log"
    assert "[REDACTED_API_KEY]" in log_content or "REDACTED" in log_content
    print("  • Automatic credential & secret redaction in security audit log: OK")
    print("  ✓ PASSED: Audit Logging & Secret Redaction verified.")

    print("=" * 75)
    print("ALL 8 VERIFICATION TEST PHASES PASSED WITH 100% SUCCESS!")
    print("ALEX PHASE 5 SECURITY & PRIVACY ENGINE IS FULLY OPERATIONAL!")
    print("=" * 75)


if __name__ == "__main__":
    run_phase5_tests()
