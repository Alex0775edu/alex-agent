"""
core/instance_manager.py — Bulletproof Single-Instance Mutex & Process Coordinator for ALEX.

Ensures:
  1. Only ONE instance of ALEX runs at any time on the system.
  2. Uses Windows Kernel32 Named Mutex ('Global\\ALEX_AI_ASSISTANT_INSTANCE_MUTEX').
  3. Cross-platform fallback: File lock with active PID inspection.
  4. Automatic stale-lock cleanup if a previous instance crashed.
  5. Clean shutdown hook to release locks.

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
LOCK_FILE = BASE_DIR / "memory" / "alex_instance.lock"
STARTUP_LOG = BASE_DIR / "memory" / "startup.log"

MUTEX_NAME = "Global\\ALEX_AI_ASSISTANT_INSTANCE_MUTEX"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


def log_startup_event(level: str, message: str) -> None:
    """Appends an event to memory/startup.log for auditing and failure diagnosis."""
    try:
        STARTUP_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] [{level.upper()}] {message}\n"
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def is_process_running(pid: int) -> bool:
    """Checks if a given process ID is genuinely running."""
    try:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def acquire_single_instance(app_name: str = "ALEX") -> bool:
    """
    Attempts to acquire exclusive single-instance ownership.
    Returns True if this is the ONLY running instance.
    Returns False if an instance is ALREADY running.
    """
    global _mutex_handle

    # 1. Windows Named Mutex Check
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_err = kernel32.GetLastError()
            if last_err == ERROR_ALREADY_EXISTS:
                log_startup_event("WARN", f"Duplicate instance blocked via Windows Mutex '{MUTEX_NAME}'.")
                return False
        except Exception as e:
            log_startup_event("WARN", f"Windows Mutex initialization exception: {e}")

    # 2. File Lock & PID Inspection (Secondary / Cross-Platform Defense)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            content = LOCK_FILE.read_text(encoding="utf-8").strip()
            parts = content.split(":")
            old_pid = int(parts[0]) if parts and parts[0].isdigit() else -1
            if old_pid > 0 and old_pid != os.getpid() and is_process_running(old_pid):
                log_startup_event("WARN", f"Duplicate instance blocked: Process {old_pid} is already active.")
                return False
            else:
                # Stale lock from crashed or terminated process
                log_startup_event("INFO", f"Cleared stale lockfile from dead process {old_pid}.")
        except Exception as e:
            log_startup_event("WARN", f"Error reading lockfile: {e}")

    # Record current instance
    try:
        LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
        log_startup_event("INFO", f"Acquired single-instance lock for PID {os.getpid()}.")
        return True
    except Exception as e:
        log_startup_event("ERROR", f"Failed to write lockfile: {e}")
        return True  # If file cannot be written, allow app to proceed


def release_single_instance() -> None:
    """Releases mutex and cleans up PID lockfile upon shutdown."""
    global _mutex_handle
    if sys.platform == "win32" and _mutex_handle:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
        except Exception:
            pass

    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass
    log_startup_event("INFO", f"Released single-instance lock for PID {os.getpid()}.")

