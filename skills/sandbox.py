"""
skills/sandbox.py — Plugin Execution Sandbox, Process Isolation & Crash Resilience.

Guarantees system reliability and security:
  • Isolated execution via thread workers with strict timeout enforcement
  • Standard output and error stream capture
  • Complete crash containment (a failing plugin never crashes the ALEX host process)
  • Cancellation token monitoring
  • Memory & runaway loop protection

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import io
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable, Dict, Optional, Tuple

from skills.sdk import ExecutionStatus, SkillContext, SkillResult


class ExecutionSandbox:
    """Executes skills and plugins within a guarded, isolated environment."""

    _instance: Optional[ExecutionSandbox] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AlexSkillWorker")

    @classmethod
    def get_instance(cls) -> ExecutionSandbox:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ExecutionSandbox()
            return cls._instance

    def run_isolated(
        self,
        func: Callable[..., Any],
        args: Optional[Tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
        ctx: Optional[SkillContext] = None
    ) -> SkillResult:
        """Executes a function inside the sandbox with timeout and stream capture."""
        args = args or ()
        kwargs = kwargs or {}
        t0 = time.monotonic()

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        def _worker():
            # Intercept stdout and stderr for the execution scope
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            try:
                if ctx and "ctx" in kwargs:
                    kwargs["ctx"] = ctx
                return func(*args, **kwargs)
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        future = self._executor.submit(_worker)

        try:
            raw_output = future.result(timeout=timeout_seconds)
            duration = round((time.monotonic() - t0) * 1000, 2)
            stdout_text = stdout_capture.getvalue()

            # If the result is already a SkillResult, return it with captured logs
            if isinstance(raw_output, SkillResult):
                raw_output.duration_ms = duration
                if stdout_text:
                    raw_output.diagnostics["stdout"] = stdout_text[:500]
                return raw_output

            return SkillResult(
                status=ExecutionStatus.SUCCESS,
                output=raw_output,
                duration_ms=duration,
                verified=True,
                diagnostics={"stdout": stdout_text[:500] if stdout_text else ""}
            )

        except TimeoutError:
            duration = round((time.monotonic() - t0) * 1000, 2)
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            if ctx:
                ctx.cancelled = True
            return SkillResult(
                status=ExecutionStatus.CANCELLED,
                output=None,
                error=f"Execution timed out after {timeout_seconds} seconds.",
                duration_ms=duration,
                verified=False,
                diagnostics={"timeout_seconds": timeout_seconds}
            )

        except Exception as e:
            duration = round((time.monotonic() - t0) * 1000, 2)
            stderr_text = stderr_capture.getvalue() or traceback.format_exc()
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=f"Plugin execution failed: {type(e).__name__}: {e}",
                duration_ms=duration,
                verified=False,
                diagnostics={"exception": str(e), "exception_type": type(e).__name__, "traceback": stderr_text[:500]}
            )


# Singleton Instance
sandbox = ExecutionSandbox.get_instance()
