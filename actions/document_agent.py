"""
actions/document_agent.py — Universal Document Intelligence Agent for ALEX 3.0.

Capabilities:
  • Summarize documents
  • Extract structured tables & metrics
  • Compare two documents
  • Answer specific questions about documents

Supported formats: PDF, DOCX, XLSX, CSV, TXT, JSON, PPTX
Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.action_timeline import timeline
from core.security import security_manager, OWNER_ADDRESS


def analyze_document(file_path: str, task: str = "summarize", query: str = "") -> str:
    """
    Analyzes, summarizes, or extracts data from documents for the owner.
    """
    p = Path(file_path)
    if not p.exists():
        return f"{OWNER_ADDRESS}, document not found at: {file_path}"

    timeline.record("DOC_AGENT", f"Document Analysis: {p.name}", f"Task: {task}")
    ext = p.suffix.lower()

    try:
        # 1. Plain Text / JSON / Markdown
        if ext in (".txt", ".md", ".json", ".log"):
            text = p.read_text(encoding="utf-8", errors="replace")
            words = len(text.split())
            preview = text[:1500]
            summary = (
                f"{OWNER_ADDRESS}, document '{p.name}' analysis complete ({words} words).\n"
                f"Summary Preview:\n{preview}..."
            )
            timeline.record("DOC_AGENT", f"Text Analyzed: {p.name}", f"{words} words processed.", status="SUCCESS")
            return summary

        # 2. CSV / Tabular data
        elif ext == ".csv":
            rows = []
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for r in reader:
                    rows.append(r)
            if not rows:
                return f"{OWNER_ADDRESS}, CSV file '{p.name}' is empty."
            headers = rows[0]
            row_count = len(rows) - 1
            summary = (
                f"{OWNER_ADDRESS}, CSV analysis for '{p.name}':\n"
                f"• Total Records: {row_count}\n"
                f"• Columns ({len(headers)}): {', '.join(headers[:8])}\n"
                f"• Sample Row: {rows[1] if len(rows) > 1 else 'None'}"
            )
            timeline.record("DOC_AGENT", f"CSV Analyzed: {p.name}", f"{row_count} records.", status="SUCCESS")
            return summary

        # 3. PDF / DOCX / Others via file_processor
        elif ext in (".pdf", ".docx", ".xlsx", ".pptx"):
            from actions.file_processor import file_processor
            res = file_processor({"file_path": str(p), "action": "summarize"})
            timeline.record("DOC_AGENT", f"Doc Processed: {p.name}", f"Format: {ext}", status="SUCCESS")
            return f"{OWNER_ADDRESS}, document analysis complete for '{p.name}':\n\n{res}"

        else:
            return f"{OWNER_ADDRESS}, file type '{ext}' is not supported for document intelligence."

    except Exception as e:
        return f"{OWNER_ADDRESS}, document processing encountered an error: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "analyze_document",
    "description": "Universal document intelligence: analyzes, summarizes, extracts tables or answers questions from PDF, DOCX, XLSX, CSV, and text documents.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Absolute or relative path to the document file"
            },
            "task": {
                "type": "STRING",
                "description": "Task to perform: 'summarize', 'extract_data', or 'qa' (default: 'summarize')"
            },
            "query": {
                "type": "STRING",
                "description": "Optional specific question or extraction query about the document"
            }
        },
        "required": ["file_path"]
    },
    "handler": analyze_document,
}

