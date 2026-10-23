"""
dev_lab/db_api_diagnostics.py — Database Integrity, Query Analysis & API Diagnostics.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatabaseApiDiagnostics:
    """Diagnostic tool for checking SQLite and local API configurations safely:

    - Integrity checks on database files
    - Masking of all credentials & secrets
    - Verification of schemas and indexes
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def audit_sqlite_databases(self) -> List[Dict[str, Any]]:
        """Find SQLite databases in project and perform non-destructive integrity audit."""
        results: List[Dict[str, Any]] = []

        for p in self.root.rglob("*.db"):
            if ".git" in str(p) or ".alex_checkpoints" in str(p):
                continue
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                # Read-only URI check
                uri = f"file:{p.resolve()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cursor = conn.cursor()

                # Run integrity check
                cursor.execute("PRAGMA integrity_check;")
                row = cursor.fetchone()
                status = row[0] if row else "unknown"

                # Count tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]

                # Check indexes count
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
                indexes = [r[0] for r in cursor.fetchall()]

                conn.close()

                results.append({
                    "database_file": rel,
                    "integrity_status": status,
                    "is_healthy": status.lower() == "ok",
                    "tables_count": len(tables),
                    "tables": tables,
                    "indexes_count": len(indexes),
                })
            except Exception as e:
                results.append({
                    "database_file": rel,
                    "integrity_status": f"Error: {e}",
                    "is_healthy": False,
                    "tables_count": 0,
                    "tables": [],
                    "indexes_count": 0,
                })

        return results

    def audit_api_endpoints(self) -> List[Dict[str, Any]]:
        """Scan project for exposed route definitions and configuration schemas."""
        endpoints: List[Dict[str, Any]] = []
        route_patterns = [
            (r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', "FastAPI/Flask"),
            (r'(?:app|router)\.(get|post|put|delete|use)\s*\(\s*["\']([^"\']+)["\']', "Express"),
        ]

        import re
        for p in self.root.rglob("*.py"):
            if ".git" in str(p) or ".alex_checkpoints" in str(p):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for pattern, framework in route_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for m in matches:
                        method = m.group(1).upper()
                        path = m.group(2)
                        endpoints.append({
                            "file": str(p.relative_to(self.root)).replace("\\", "/"),
                            "method": method,
                            "path": path,
                            "framework": framework,
                        })
            except Exception:
                pass

        return endpoints

    def sanitize_connection_string(self, conn_str: str) -> str:
        """Strip passwords and tokens from connection URLs."""
        import re
        # e.g. postgresql://user:password@localhost:5432/db -> postgresql://user:***@localhost:5432/db
        sanitized = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***REDACTED***@', conn_str)
        return sanitized

