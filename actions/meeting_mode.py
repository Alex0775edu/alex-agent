"""
actions/meeting_mode.py — Meeting Transcription & Summary Engine for ALEX 3.0.

Capabilities:
  • Transcribes or accepts meeting notes
  • Extracts key decisions & action items
  • Formats executive meeting summary for Aditya Sir

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import time
from pathlib import Path
from core.action_timeline import timeline
from core.security import security_manager, OWNER_ADDRESS


def process_meeting_notes(transcript_text: str, title: str = "Team Meeting") -> str:
    """
    Summarizes meeting transcripts, extracting key decisions and action items.
    """
    timeline.record("MEETING", f"Meeting Processed: {title}", f"Transcript length: {len(transcript_text)} chars")

    lines = [line.strip() for line in transcript_text.split("\n") if line.strip()]
    if not lines:
        return f"{OWNER_ADDRESS}, meeting transcript text empty hai."

    # Decision extraction heuristics
    decisions = []
    actions = []
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ("decided", "agreed", "finalized", "conclusion", "decision")):
            decisions.append(line)
        elif any(kw in lower for kw in ("todo", "action", "task", "assign", "will do", "karna hai", "deadline")):
            actions.append(line)

    summary = (
        f"═══════════════════════════════════════════\n"
        f"ALEX 3.0 MEETING BRIEFING: {title}\n"
        f"Date: {time.strftime('%Y-%m-%d')}\n"
        f"═══════════════════════════════════════════\n\n"
        f"📌 KEY DECISIONS:\n"
        + ("\n".join(f"  • {d}" for d in decisions) if decisions else "  • No explicit decisions flagged.")
        + "\n\n"
        f"✅ ACTION ITEMS & TASKS:\n"
        + ("\n".join(f"  • {a}" for a in actions) if actions else "  • General review and follow-up pending.")
        + f"\n\nTotal points reviewed: {len(lines)}"
    )

    timeline.record("MEETING", f"Meeting Summary Generated: {title}", f"{len(decisions)} decisions, {len(actions)} actions", status="SUCCESS")
    return summary


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "meeting_mode",
    "description": "Processes meeting transcripts or notes to extract executive summaries, key decisions, and actionable task items for Aditya Sir.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "transcript_text": {
                "type": "STRING",
                "description": "Full meeting transcription or notes text"
            },
            "title": {
                "type": "STRING",
                "description": "Title of the meeting (default: 'Team Meeting')"
            }
        },
        "required": ["transcript_text"]
    },
    "handler": process_meeting_notes,
}

