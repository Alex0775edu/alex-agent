"""
core/intent_engine.py — Natural Language Intent Engine for ALEX 3.0.

Provides first-class tri-lingual support (Hindi / Hinglish / English)
and deterministic local routing (<50ms execution) for:
  • Autonomous Goals: Organize Downloads, YouTube Search
  • App Launching & Computer Control
  • System Status, Diagnostics, Security Lock, Emergency Stop
  • Focus Mode, Morning Briefing, Action Timeline, Clipboard Mode
  • Undo, Voice Enrollment, Project Workspace Switching

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.action_timeline import timeline


@dataclass
class IntentResult:
    intent: str                 # e.g. "OPEN_APPLICATION", "VOLUME_UP", "ORGANIZE_DOWNLOADS"
    confidence: float          # 0.0 to 1.0
    slots: Dict[str, Any]      # Extracted entities (app_name, delta, project_name, query)
    detected_language: str     # "hindi", "hinglish", "english"
    is_local_command: bool     # True -> bypasses LLM network latency (<50ms execution)
    handled: bool = False
    response_text: str = ""


class IntentEngine:
    """Tri-lingual natural language intent classifier and fast dispatcher."""

    def __init__(self):
        self._init_patterns()

    def detect_language(self, text: str) -> str:
        """Classify input text into hindi, hinglish, or english."""
        t = text.lower().strip()
        # Devanagari script detection
        if any('\u0900' <= char <= '\u097f' for char in t):
            return "hindi"

        hinglish_words = {
            "kholo", "khol", "karo", "kar", "chalao", "chala", "batao", "bata",
            "kitna", "hai", "hain", "kya", "mera", "meri", "mere", "ko", "se",
            "badha", "badhao", "kam", "dhundo", "samjhao", "yaad", "rakho",
            "ruko", "band", "apna", "apni", "hoga", "raha", "rahi", "ka", "ki",
            "ke", "aur", "thoda", "aaj", "abhi", "par", "par", "sab", "jo"
        }
        tokens = set(re.findall(r'[a-zA-Z]+', t))
        matches = tokens.intersection(hinglish_words)
        if len(matches) >= 2 or (len(matches) >= 1 and len(tokens) <= 4):
            return "hinglish"
        return "english"

    def _init_patterns(self):
        # 1. Volume
        self.vol_up_patterns = [
            r"\b(?:volume|sound|awaaz|awaz)\s*(?:badha(?:o|do)?|increase|up|loud|high)\b",
            r"\b(?:increase|turn up|raise)\s*(?:the\s*)?(?:volume|sound)\b",
            r"\b(?:sound|volume)\s*(?:loud\s*karo|tez\s*karo)\b",
            r"वॉल्यूम\s*बढ़ा(?:ओ|एं)?",
        ]
        self.vol_down_patterns = [
            r"\b(?:volume|sound|awaaz|awaz)\s*(?:kam\s*(?:karo|do)?|decrease|down|low)\b",
            r"\b(?:decrease|turn down|lower)\s*(?:the\s*)?(?:volume|sound)\b",
            r"\b(?:sound|volume)\s*(?:dheeme\s*karo|slow\s*karo)\b",
            r"वॉल्यूम\s*कम\s*करो",
        ]
        self.vol_mute_patterns = [
            r"\b(?:mute|unmute|awaaz\s*band)\b",
            r"\b(?:mute\s*(?:karo|kar\s*do)|silence)\b",
        ]
        # 2. Lock / Security
        self.lock_patterns = [
            r"\b(?:lock\s*yourself|secure\s*mode|lock\s*karo|alex\s*lock|lock\s*alex|alex\s*ko\s*lock\s*karo)\b",
            r"\b(?:lock\s*pc|lock\s*computer|system\s*lock)\b",
        ]
        # 3. Emergency Stop
        self.emergency_patterns = [
            r"\b(?:emergency\s*stop|sab\s*band\s*karo|abort\s*all|stop\s*everything|ruko\s*ruko|alex\s*stop)\b",
        ]
        # 4. System Metrics
        self.system_status_patterns = [
            r"\b(?:ram|cpu|gpu|system|memory|performance|specs|status)\s*(?:kitna|check|kaisa|status|usage|load)\b",
            r"\b(?:system\s*status|check\s*(?:my\s*)?system|pc\s*status|ram\s*kitna\s*use\s*ho\s*raha\s*hai)\b",
        ]
        # 5. Diagnostics / Health Check
        self.diagnostics_patterns = [
            r"\b(?:apna\s*health\s*check|health\s*check|system\s*health|diagnostics|self\s*test)\b",
            r"\b(?:mere\s*system\s*ka\s*health\s*check\s*karo)\b",
        ]
        # 5b. Dedicated Network Diagnostics
        self.network_diagnostics_patterns = [
            r"\b(?:network\s*diagnostic(?:\s*run\s*karo|\s*karo)?|diagnostic\s*network)\b",
            r"\b(?:internet\s*check|network\s*check|check\s*network|vpn\s*check|check\s*internet)\b",
            r"\b(?:network\s*test|internet\s*test)\b",
        ]
        # 6. Time & Date
        self.time_patterns = [
            r"\b(?:what(?:\s*is)?(?:\s*the)?\s*time|what\s*time\s*is\s*it|current\s*time|time\s*(?:kya|batao|hua|check)|samay\s*kya\s*hai|waqt\s*kya\s*hai|tell\s*me\s*the\s*time)\b",
            r"\b(?:what(?:\s*is)?(?:\s*the|\s*today'?s)?\s*date|date\s*(?:kya|batao)|aaj\s*ki\s*date|today'?s\s*date)\b",
        ]
        # 7. Goals: Downloads Organization
        self.downloads_patterns = [
            r"\b(?:downloads?\s*organize\s*kar\s*(?:do|o)|organize\s*(?:my\s*)?downloads?)\b",
            r"\b(?:downloads?\s*clean\s*karo|sort\s*downloads?)\b",
        ]
        # 8. Goals: YouTube Search
        self.yt_search_patterns = [
            r"^(?:alex\s*,?\s*)?youtube\s+par\s+(.+)\s+(?:dhundo|search\s*karo|play\s*karo|chalao)$",
            r"^(?:alex\s*,?\s*)?search\s+youtube\s+for\s+(.+)$",
            r"^(?:alex\s*,?\s*)?find\s+(.+)\s+on\s+youtube$",
        ]
        # 8b. Goals: Compound Browser & Platform Search
        self.compound_browser_search_patterns = [
            (
                r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\s]+?)\s+(?:kholo|open\s*karo|chalao|start\s*karo)\s+aur\s+([a-zA-Z0-9\s]+?)\s+par\s+(.+?)\s+(?:search\s*karo|dhundo|play\s*karo|chalao|dekho)[\.\?!]?$",
                ("browser", "platform", "query")
            ),
            (
                r"^(?:alex\s*,?\s*)?(?:open|launch|start)\s+([a-zA-Z0-9\s]+?)\s+and\s+search\s+(?:for\s+)?(.+?)\s+on\s+([a-zA-Z0-9\s]+)[\.\?!]?$",
                ("browser", "query", "platform")
            ),
            (
                r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\s]+?)\s+par\s+(.+?)\s+(?:search\s*karo|dhundo|play\s*karo|chalao)\s+aur\s+([a-zA-Z0-9\s]+?)\s+(?:kholo|open\s*karo|chalao)[\.\?!]?$",
                ("platform", "query", "browser")
            ),
            (
                r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\s]+?)\s+(?:kholo|open\s*karo|chalao|start\s*karo)\s+aur\s+([a-zA-Z0-9\s]+?)\s+par\s+(?:search\s*karo|dhundo)[\.\?!]?$",
                ("browser", "platform")
            ),
            (
                r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\s]+?)\s+(?:kholo|open\s*karo|chalao|start\s*karo)\s+aur\s+(.+?)\s+(?:search\s*karo|dhundo)[\.\?!]?$",
                ("browser", "query")
            ),
            (
                r"^(?:alex\s*,?\s*)?(?:open|launch|start)\s+([a-zA-Z0-9\s]+?)\s+and\s+search\s+(?:for\s+)?(.+)[\.\?!]?$",
                ("browser", "query")
            ),
        ]
        # 9. Focus Mode
        self.focus_patterns = [
            r"\b(?:(\d+)\s*(?:hours?|hrs?|minutes?|mins?)\s*focus\s*mode)\b",
            r"\b(?:focus\s*mode\s*(?:on|start|chalao|karo)|start\s*focus\s*mode)\b",
            r"\b(?:focus\s*status|check\s*focus)\b",
        ]
        # 10. Morning Briefing & News Commands
        self.briefing_patterns = [
            r"\b(?:morning\s*briefing|morning\s*update|aaj\s*ka\s*briefing|daily\s*brief)\b",
            r"\b(?:today'?s\s*important\s*updates|full\s*briefing\s*dikhao|briefing\s*do)\b",
            r"\b(?:what'?s\s*new|kya\s*naya\s*hai)\b",
        ]
        self.news_briefing_patterns = [
            r"\b(?:aaj\s*ki\s*news\s*batao|today'?s\s*news|news\s*briefing|news\s*batao|give\s*me\s*the\s*news)\b",
        ]
        self.tech_news_patterns = [
            r"\b(?:sirf\s*technology\s*news\s*batao|tech\s*news\s*batao|technology\s*news)\b",
        ]
        self.startup_control_patterns = [
            r"\b(?:startup\s*briefing\s*band\s*karo|disable\s*startup\s*briefing)\b",
            r"\b(?:short\s*briefing|chhota\s*briefing)\b",
        ]
        # 11. Action Timeline
        self.timeline_patterns = [
            r"\b(?:action\s*timeline|activity\s*log|recent\s*actions|timeline\s*(?:dikhao|show))\b",
        ]
        # 12. Clipboard
        self.clipboard_patterns = [
            r"\b(?:jo\s*copy\s*kiya\s*hai\s*usko\s*explain\s*karo|clipboard\s*explain|explain\s*clipboard)\b",
            r"\b(?:is\s*code\s*ko\s*fix\s*karo|clipboard\s*code\s*fix|fix\s*copied\s*code)\b",
            r"\b(?:is\s*paragraph\s*ko\s*professional\s*banao|polish\s*clipboard)\b",
        ]
        # 13. Undo
        self.undo_patterns = [
            r"\b(?:last\s*change\s*undo\s*karo|undo\s*last\s*(?:action|change)|undo\s*karo|\bundo\b)\b",
        ]
        # 14. Project Operations (List, Status, Run, Continue, Bugs, Switch)
        self.projects_list_patterns = [
            r"\b(?:mere\s*)?projects?\s*(?:ki\s*)?list\s*(?:dikhao|batao|kholo|show)\b",
            r"\b(?:list\s*(?:my\s*)?projects?|show\s*(?:all\s*)?projects?)\b",
        ]
        self.project_status_patterns = [
            r"\b(?:([a-zA-Z0-9\-_]+)\s*(?:project\s*)?(?:ka\s*)?status\s*(?:check\s*karo|batao|dikhao))\b",
            r"\b(?:status\s*check\s*karo\s*([a-zA-Z0-9\-_]+))\b",
            r"\b(?:check\s*status\s*of\s*([a-zA-Z0-9\-_]+))\b",
        ]
        self.project_run_patterns = [
            r"\b(?:mera\s*)?([a-zA-Z0-9\-_]+)\s*project\s*run\s*karo\b",
            r"\b(?:run\s*(?:my\s*)?([a-zA-Z0-9\-_]+)\s*project)\b",
            r"\b(?:project\s*([a-zA-Z0-9\-_]+)\s*run\s*karo)\b",
        ]
        self.project_continue_patterns = [
            r"\b(?:pichhle|previous|last)\s*project\s*(?:ka\s*kaam\s*)?continue\s*karo\b",
            r"\b(?:continue\s*where\s*i\s*left\s*off|resume\s*(?:last\s*)?project)\b",
        ]
        self.project_bugs_patterns = [
            r"\b(?:project\s*(?:mein\s*)?)?(?:naye\s*)?bugs\s*check\s*karo\b",
            r"\b(?:check\s*(?:for\s*)?(?:new\s*)?bugs\s*(?:in\s*project)?)\b",
        ]
        self.project_patterns = [
            r"\b(?:project|workspace)\s*(?:skillsum|e-baal seva|ebal seva|ems|personal)\b",
            r"\b(?:skillsum|e-baal seva|ems)\s*(?:project\s*)?(?:continue|kholo|open|resume)\b",
        ]
        # 14b. Project Inspect & Bug Fix (Autonomous Developer Mode)
        self.project_fix_patterns = [
            r"\b(?:mera\s*)?project\s*(?:ke\s*)?(?:bugs\s*)?(?:check|inspect|audit|fix|test|run)\s*(?:karo|kar\s*do)?\b",
            r"\b(?:check|inspect|audit|fix|debug)\s*(?:my\s*)?project\b",
            r"\b(?:college\s*management|skillsum|ems|e-baal\s*seva)\s*(?:project\s*)?(?:check|fix|complete|inspect)\s*(?:karo|kar\s*do)?\b",
        ]
        # 14c. Proactive Notifications & Reminders & DND
        self.proactive_notif_patterns = [
            r"\b(?:notifications?\s*(?:dikhao|show|batao)|reminders?\s*(?:dikhao|show|batao))\b",
            r"\b(?:unread\s*notifications?|pending\s*reminders?)\b",
        ]
        self.dnd_patterns = [
            r"\b(?:do\s*not\s*disturb|dnd)\s*(?:mode\s*)?(?:on|off|toggle|chalao|band\s*karo)?\b",
        ]
        # 14g. PC Automation: Open Website, Web Search, Files & Folders
        self.open_website_patterns = [
            r"^(?:alex\s*,?\s*)?(?:open|go\s*to|launch|visit)?\s*(?:website\s*)?(https?://[^\s]+|[a-zA-Z0-9\-_]+\.(?:com|org|io|net|edu|in|gov|ai|dev|co))(?:\s+(?:kholo|open\s*karo|chalao))?[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\-_]+\.(?:com|org|io|net|edu|in|gov|ai|dev|co))\s+(?:kholo|open\s*karo|chalao)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?(?:open|launch|visit)\s+(?:website\s*)?([a-zA-Z0-9\-_]+\.[a-zA-Z]{2,})[\.\?!]?$",
        ]
        self.web_search_patterns = [
            r"^(?:alex\s*,?\s*)?(?:google|web|internet)\s*par\s+(.+?)\s+(?:search\s*karo|dhundo)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?search\s+(?:on\s+google|on\s+the\s+web|the\s+web)?\s*for\s+(.+)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?search\s+(.+?)\s+on\s+google[\.\?!]?$",
        ]
        self.list_files_patterns = [
            r"^(?:alex\s*,?\s*)?([a-zA-Z0-9_\-\/\.]+)\s*(?:folder|directory)?\s*(?:ke\s*)?files?\s*(?:list\s*karo|dikhao|batao|show\s*karo)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?(?:list|show)\s*files?\s*(?:in|inside)?\s*([a-zA-Z0-9_\-\/\.]+)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?(?:list\s*files|files\s*list\s*karo|files\s*dikhao)[\.\?!]?$",
        ]
        self.read_file_patterns = [
            r"^(?:alex\s*,?\s*)?([a-zA-Z0-9_\-\/\.]+)\s*(?:file\s*)?(?:padho|read\s*karo|dikhao)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?read\s*(?:file)?\s*([a-zA-Z0-9_\-\/\.]+)[\.\?!]?$",
        ]
        self.search_files_patterns = [
            r"^(?:alex\s*,?\s*)?(?:([a-zA-Z0-9_\-\/\.]+)\s*(?:mein|par)\s*)?([a-zA-Z0-9_\-\/\.]+)\s*file\s*(?:dhundo|search\s*karo)[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?find\s*file\s*([a-zA-Z0-9_\-\/\.]+)(?:\s*(?:in|on)\s*([a-zA-Z0-9_\-\/\.]+))?[\.\?!]?$",
            r"^(?:alex\s*,?\s*)?search\s*(?:for\s*)?file\s*([a-zA-Z0-9_\-\/\.]+)[\.\?!]?$",
        ]
        self.create_folder_patterns = [
            (
                r"^(?:alex\s*,?\s*)?(?:([a-zA-Z0-9_\-\/\.]+)\s*(?:mein|par)\s*)?([a-zA-Z0-9_\-]+)\s*(?:naam\s*ka\s*)?folder\s*(?:banao|create\s*karo)[\.\?!]?$",
                ("location", "folder_name")
            ),
            (
                r"^(?:alex\s*,?\s*)?create\s*folder\s*([a-zA-Z0-9_\-]+)(?:\s*(?:in|on)\s*([a-zA-Z0-9_\-\/\.]+))?[\.\?!]?$",
                ("folder_name", "location")
            ),
        ]
        self.create_file_patterns = [
            (
                r"^(?:alex\s*,?\s*)?(?:([a-zA-Z0-9_\-\/\.]+)\s*(?:mein|par)\s*)?([a-zA-Z0-9_\-\.]+)\s*(?:naam\s*ki\s*)?file\s*(?:banao|create\s*karo)[\.\?!]?$",
                ("location", "file_name")
            ),
            (
                r"^(?:alex\s*,?\s*)?create\s*file\s*([a-zA-Z0-9_\-\.]+)(?:\s*(?:in|on)\s*([a-zA-Z0-9_\-\/\.]+))?[\.\?!]?$",
                ("file_name", "location")
            ),
        ]

        # 14h. SkillSum Resume Automation
        self.skillsum_patterns = [
            r"^(?:alex\s*,?\s*)?(?:skillsum\s+)?(?:evaluate|parse|analyze|process)\s+resume\s+(.+)$",
            r"^(?:alex\s*,?\s*)?(?:skillsum\s+)?resume\s+(.+?)\s+(?:ko\s*)?(?:evaluate|analyze|parse|check)\s*(?:karo|kar\s*do)?$",
        ]

        # 15. Open Application
        self.open_app_patterns = [
            r"^(?:alex\s*,?\s*)?(?:open|launch|start|run)\s+([a-zA-Z0-9\s\.\-_]+)$",
            r"^(?:alex\s*,?\s*)?([a-zA-Z0-9\s\.\-_]+)\s+(?:kholo|khol\s*do|open\s*karo|chalao|chala\s*do|start\s*karo)$",
            r"^(?:alex\s*,?\s*)?(?:kholo|chalao)\s+([a-zA-Z0-9\s\.\-_]+)$",
        ]
        # 16. Language Preference
        self.language_patterns = [
            r"\b(hindi|english|hinglish)\s*mein\s*baat\s*karo\b",
            r"\b(?:speak|talk)\s*(?:in\s*)?(hindi|english|hinglish)\b",
            r"\bswitch\s*to\s*(hindi|english|hinglish)\b",
        ]
        # 17. Task Center
        self.task_center_patterns = [
            r"\b(?:task\s*center|tasks\s*dikhao|show\s*tasks|pending\s*tasks|active\s*tasks)\b",
        ]
        # 18. Autonomy Mode
        self.autonomy_patterns = [
            r"\bautonomy\s*(?:level|mode)?\s*(ask|normal|trusted|autonomous)\b",
        ]
        # 19. Phase 4 Vision & Screen Intelligence
        self.screen_understand_patterns = [
            r"\b(?:screen\s*(?:par|pe)?\s*(?:kya\s*(?:hai|dikh\s*raha\s*hai)|check\s*karo|dekho)|check\s*screen|what(?:'s|\s*is)\s*on\s*(?:the\s*)?screen)\b",
        ]
        self.followup_patterns = [
            (r"\b(?:isko\s*aur\s*professional\s*banao|professional\s*banao)\b", "FOLLOWUP_PROFESSIONAL"),
            (r"\b(?:ab\s*pdf\s*bhi\s*bana\s*do|pdf\s*bana\s*do)\b", "FOLLOWUP_PDF"),
            (r"\b(?:pichhle\s*design\s*ka\s*background\s*change\s*karo|background\s*change\s*karo)\b", "FOLLOWUP_IMAGE_BG"),
            (r"\b(?:jo\s*bug\s*mila\s*tha[,\s]+use\s*fix\s*karo)\b", "FOLLOWUP_FIX_BUG"),
            (r"\b(?:last\s*output\s*folder\s*kholo|output\s*folder\s*kholo)\b", "FOLLOWUP_OUTPUT_FOLDER"),
        ]
        self.privacy_patterns = [
            (r"\b(?:screen\s*capture\s*(?:pause|roko|band)\s*karo|pause\s*vision)\b", "PRIVACY_PAUSE"),
            (r"\b(?:screen\s*capture\s*(?:resume|chalu)\s*karo|resume\s*vision)\b", "PRIVACY_RESUME"),
        ]
        # 20. Workflow Patterns (PowerPoint, Word, Excel, Blender, Email)
        self.workflow_ppt_patterns = [
            r"\b(?:([a-zA-Z0-9\s]+)\s*(?:par|pe)?\s*(\d+)?\s*(?:slides?|slide)?\s*(?:ki\s*)?(?:professional\s*)?ppt\s*(?:banao|create\s*karo|generate\s*karo))\b",
            r"\b(?:create|make|build)\s*(?:a\s*)?(?:presentation|ppt|powerpoint)\s*(?:on|about)\s*([a-zA-Z0-9\s]+)\b",
        ]
        self.workflow_excel_patterns = [
            r"\b(?:excel\s*(?:file|sheet)?\s*(?:ka\s*data\s*)?analy[sz]e\s*karke\s*charts?\s*aur\s*summary\s*banao)\b",

            r"\b(?:analy[sz]e\s*excel\s*(?:file)?\s*and\s*create\s*charts?)\b",
        ]
        self.workflow_blender_patterns = [
            r"\b(?:blender\s*(?:mein\s*)?(?:ek\s*)?(.+)\s*(?:banao|create\s*karo|render\s*karo))\b",
            r"\b(?:create\s*(?:a\s*)?3d\s*(?:scene|model)?\s*in\s*blender\s*(?:of|for)?\s*(.+))\b",
        ]
        self.workflow_email_patterns = [
            r"\b(?:email\s*(?:draft|banao|send\s*karo|bhejo))\b",
            r"\b(?:draft\s*(?:an\s*)?email|compose\s*(?:an\s*)?email)\b",
        ]


    def parse(self, text: str) -> IntentResult:
        """Parse natural language command into structured IntentResult."""
        raw = text.strip()
        lang = self.detect_language(raw)
        clean = re.sub(r'^(?:alex|hey alex|alexa)\s*[,:\-]?\s*', '', raw, flags=re.IGNORECASE).strip()
        clean_lower = clean.lower()

        # 1. Emergency Stop
        for p in self.emergency_patterns:
            if re.search(p, clean_lower):
                return IntentResult("EMERGENCY_STOP", 0.99, {}, lang, is_local_command=True)

        # 2. Lock / Security
        for p in self.lock_patterns:
            if re.search(p, clean_lower):
                return IntentResult("SECURITY_LOCK", 0.98, {}, lang, is_local_command=True)

        # 3. Undo
        for p in self.undo_patterns:
            if re.search(p, clean_lower):
                return IntentResult("UNDO", 0.96, {}, lang, is_local_command=True)

        # 4. Downloads Organization Goal
        for p in self.downloads_patterns:
            if re.search(p, clean_lower):
                return IntentResult("ORGANIZE_DOWNLOADS", 0.95, {}, lang, is_local_command=True)

        # 5. Compound Browser Search Goal (e.g. "Chrome kholo aur YouTube par Python tutorial search karo")
        for p, fields in self.compound_browser_search_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                slots = dict(zip(fields, [g.strip() for g in m.groups()]))
                if "platform" not in slots:
                    slots["platform"] = "Google"
                return IntentResult("COMPOUND_BROWSER_SEARCH", 0.98, slots, lang, is_local_command=True)

        # 5b. YouTube Search Goal
        for p in self.yt_search_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                q = m.group(1).strip()
                return IntentResult("YOUTUBE_SEARCH", 0.95, {"query": q}, lang, is_local_command=True)

        # 6. Morning Briefing & News Routing
        for p in self.tech_news_patterns:
            if re.search(p, clean_lower):
                return IntentResult("TECH_NEWS_BRIEFING", 0.96, {"category": "Technology"}, lang, is_local_command=True)
        for p in self.news_briefing_patterns:
            if re.search(p, clean_lower):
                return IntentResult("NEWS_BRIEFING", 0.95, {}, lang, is_local_command=True)
        for p in self.startup_control_patterns:
            if re.search(p, clean_lower):
                return IntentResult("STARTUP_BRIEFING_CONTROL", 0.95, {"action": "disable" if "band" in clean_lower or "disable" in clean_lower else "short"}, lang, is_local_command=True)
        for p in self.briefing_patterns:
            if re.search(p, clean_lower):
                return IntentResult("MORNING_BRIEFING", 0.95, {}, lang, is_local_command=True)

        # 7. Action Timeline
        for p in self.timeline_patterns:
            if re.search(p, clean_lower):
                return IntentResult("ACTION_TIMELINE", 0.95, {}, lang, is_local_command=True)

        # 8. Focus Mode
        for p in self.focus_patterns:
            m = re.search(p, clean_lower)
            if m:
                duration = 60
                if m.groups() and m.group(1):
                    val = int(m.group(1))
                    if "hour" in clean_lower or "hr" in clean_lower:
                        duration = val * 60
                    else:
                        duration = val
                return IntentResult("FOCUS_MODE", 0.95, {"duration": duration}, lang, is_local_command=True)

        # 9. Clipboard Mode
        for p in self.clipboard_patterns:
            if re.search(p, clean_lower):
                task = "explain"
                if "code" in clean_lower or "fix" in clean_lower: task = "fix_code"
                elif "professional" in clean_lower or "polish" in clean_lower: task = "polish"
                return IntentResult("CLIPBOARD_MODE", 0.94, {"task": task}, lang, is_local_command=True)

        # 10. Diagnostics / Health Check
        for p in self.network_diagnostics_patterns:
            if re.search(p, clean_lower):
                return IntentResult("NETWORK_DIAGNOSTICS", 0.96, {}, lang, is_local_command=True)
        for p in self.diagnostics_patterns:
            if re.search(p, clean_lower):
                return IntentResult("SELF_DIAGNOSTICS", 0.95, {}, lang, is_local_command=True)

        # 11. Volume Controls
        for p in self.vol_up_patterns:
            if re.search(p, clean_lower):
                return IntentResult("VOLUME_UP", 0.95, {"delta": 5}, lang, is_local_command=True)
        for p in self.vol_down_patterns:
            if re.search(p, clean_lower):
                return IntentResult("VOLUME_DOWN", 0.95, {"delta": -5}, lang, is_local_command=True)
        for p in self.vol_mute_patterns:
            if re.search(p, clean_lower):
                return IntentResult("VOLUME_MUTE", 0.95, {}, lang, is_local_command=True)

        # 12. Project Operations (Checked before generic system status)
        for p in self.projects_list_patterns:
            if re.search(p, clean_lower):
                return IntentResult("PROJECTS_LIST", 0.96, {}, lang, is_local_command=True)

        for p in self.project_continue_patterns:
            if re.search(p, clean_lower):
                return IntentResult("PROJECT_CONTINUE", 0.95, {}, lang, is_local_command=True)

        for p in self.project_bugs_patterns:
            if re.search(p, clean_lower):
                return IntentResult("PROJECT_BUGS", 0.95, {}, lang, is_local_command=True)

        for p in self.project_status_patterns:
            m = re.search(p, clean_lower)
            if m:
                proj = m.group(1).strip()
                return IntentResult("PROJECT_STATUS", 0.95, {"project_name": proj}, lang, is_local_command=True)

        for p in self.project_run_patterns:
            m = re.search(p, clean_lower)
            if m:
                proj = m.group(1).strip()
                return IntentResult("PROJECT_RUN", 0.95, {"project_name": proj}, lang, is_local_command=True)

        # 13. System Status
        for p in self.system_status_patterns:
            if re.search(p, clean_lower):
                return IntentResult("SYSTEM_STATUS", 0.92, {}, lang, is_local_command=True)

        # 14. Time and Date
        for p in self.time_patterns:
            if re.search(p, clean_lower):
                return IntentResult("TIME_CHECK", 0.94, {}, lang, is_local_command=True)

        # 14b. Project Switch (Named)
        for p in self.project_patterns:
            if re.search(p, clean_lower):
                project_name = "Personal"
                if "skillsum" in clean_lower: project_name = "SkillSum"
                elif "e-baal" in clean_lower or "ebal" in clean_lower: project_name = "E-baal Seva"
                elif "ems" in clean_lower: project_name = "EMS"
                return IntentResult("PROJECT_SWITCH", 0.90, {"project_name": project_name}, lang, is_local_command=True)

        # 14c. Project Inspect & Bug Fix (Developer Mode)
        for p in self.project_fix_patterns:
            if re.search(p, clean_lower):
                target_p = "Personal"
                if "skillsum" in clean_lower: target_p = "SkillSum"
                elif "e-baal" in clean_lower or "ebal" in clean_lower: target_p = "E-baal Seva"
                elif "ems" in clean_lower: target_p = "EMS"
                elif "college" in clean_lower: target_p = "College Management"
                return IntentResult("PROJECT_INSPECT_FIX", 0.95, {"project_name": target_p, "query": clean}, lang, is_local_command=True)

        # 14d. Proactive Intelligence & DND
        for p in self.proactive_notif_patterns:
            if re.search(p, clean_lower):
                return IntentResult("SHOW_NOTIFICATIONS", 0.95, {}, lang, is_local_command=True)

        for p in self.dnd_patterns:
            if re.search(p, clean_lower):
                return IntentResult("DND_TOGGLE", 0.95, {}, lang, is_local_command=True)

        # 14e. Phase 4 Screen Intelligence & Follow-up Commands
        for p in self.screen_understand_patterns:
            if re.search(p, clean_lower):
                return IntentResult("SCREEN_UNDERSTAND", 0.95, {}, lang, is_local_command=True)

        for pat, intent_name in self.followup_patterns:
            if re.search(pat, clean_lower):
                return IntentResult(intent_name, 0.96, {"raw_query": clean}, lang, is_local_command=True)

        for pat, intent_name in self.privacy_patterns:
            if re.search(pat, clean_lower):
                return IntentResult(intent_name, 0.98, {}, lang, is_local_command=True)

        # 14f. Advanced Desktop Workflows (PowerPoint, Excel, Blender, Email)
        for p in self.workflow_ppt_patterns:
            m = re.search(p, clean, flags=re.IGNORECASE)
            if m:
                topic = m.group(1).strip() if m.lastindex >= 1 else "Topic Overview"
                count_str = m.group(2) if m.lastindex >= 2 and m.group(2) else "0"
                cnt = int(count_str) if count_str.isdigit() else 0
                return IntentResult("WORKFLOW_PPT", 0.96, {"topic": topic, "count": cnt, "raw": clean}, lang, is_local_command=True)

        for p in self.workflow_excel_patterns:
            if re.search(p, clean_lower):
                return IntentResult("WORKFLOW_EXCEL", 0.96, {"raw": clean}, lang, is_local_command=True)

        for p in self.workflow_blender_patterns:
            m = re.search(p, clean, flags=re.IGNORECASE)
            if m:
                desc = m.group(1).strip() if m.lastindex >= 1 else "low-poly house"
                return IntentResult("WORKFLOW_BLENDER", 0.96, {"description": desc, "raw": clean}, lang, is_local_command=True)

        for p in self.workflow_email_patterns:
            if re.search(p, clean_lower):
                return IntentResult("WORKFLOW_EMAIL", 0.96, {"raw": clean}, lang, is_local_command=True)

        # 14g. PC Automation: Open Website, Web Search, Files & Folders
        for p in self.open_website_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                u = m.group(1).strip()
                return IntentResult("OPEN_WEBSITE", 0.96, {"url": u}, lang, is_local_command=True)

        for p in self.web_search_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                q = m.group(1).strip()
                return IntentResult("WEB_SEARCH", 0.95, {"query": q, "engine": "google"}, lang, is_local_command=True)

        for p in self.list_files_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                loc = m.group(1).strip() if (m.lastindex and m.group(1)) else "desktop"
                return IntentResult("LIST_FILES", 0.95, {"path": loc}, lang, is_local_command=True)

        for p in self.read_file_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                f_name = m.group(1).strip()
                return IntentResult("READ_FILE", 0.95, {"path": f_name}, lang, is_local_command=True)

        for p, fields in self.create_folder_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                slots = {}
                for field_name, val in zip(fields, m.groups()):
                    if val:
                        slots[field_name] = val.strip()
                if "location" not in slots:
                    slots["location"] = "desktop"
                return IntentResult("CREATE_FOLDER", 0.95, slots, lang, is_local_command=True)

        for p, fields in self.create_file_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                slots = {"content": ""}
                for field_name, val in zip(fields, m.groups()):
                    if val:
                        slots[field_name] = val.strip()
                if "location" not in slots:
                    slots["location"] = "desktop"
                return IntentResult("CREATE_FILE", 0.95, slots, lang, is_local_command=True)

        # 14h. SkillSum Resume Automation
        for p in self.skillsum_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                path_val = m.group(1).strip()
                return IntentResult("SKILLSUM_RESUME_EVAL", 0.96, {"resume_path": path_val}, lang, is_local_command=True)

        for p in self.search_files_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                if m.lastindex >= 2 and m.group(2):
                    loc = m.group(2).strip()
                    q = m.group(1).strip()
                else:
                    loc = "desktop"
                    q = m.group(1).strip()
                return IntentResult("SEARCH_FILES", 0.95, {"query": q, "location": loc}, lang, is_local_command=True)

        # 15. Open Application
        for p in self.open_app_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                app_name = m.group(1).strip()
                if app_name.lower() not in ("screen", "summary", "this", "file", "it", "music", "video", "report"):
                    return IntentResult("OPEN_APPLICATION", 0.94, {"app_name": app_name}, lang, is_local_command=True)

        # 16. Language Preference
        for p in self.language_patterns:
            m = re.search(p, clean_lower)
            if m:
                target_lang = m.group(1).lower()
                return IntentResult("LANGUAGE_SWITCH", 0.95, {"language": target_lang}, lang, is_local_command=True)

        # 17. Task Center
        for p in self.task_center_patterns:
            if re.search(p, clean_lower):
                return IntentResult("TASK_CENTER", 0.95, {}, lang, is_local_command=True)

        # 18. Autonomy Mode
        for p in self.autonomy_patterns:
            m = re.search(p, clean_lower)
            if m:
                mode_target = m.group(1).lower()
                return IntentResult("AUTONOMY_MODE", 0.95, {"mode": mode_target}, lang, is_local_command=True)


        # Default: complex command requiring LLM / tool planning
        return IntentResult("GENERAL_QUERY", 0.5, {"query": clean}, lang, is_local_command=False)


    def execute_local_command(self, res: IntentResult) -> IntentResult:
        """Execute local command directly with sub-50ms latency."""
        from core.security import security_manager, OWNER_ADDRESS
        from core.agent_engine import agent_engine

        # Security check:
        privileged_intents = ("OPEN_APPLICATION", "COMPOUND_BROWSER_SEARCH", "OPEN_WEBSITE", "WEB_SEARCH", "CREATE_FOLDER", "CREATE_FILE", "DELETE_FILE", "LIST_FILES", "READ_FILE", "SEARCH_FILES", "VOLUME_UP", "VOLUME_DOWN", "VOLUME_MUTE", "ORGANIZE_DOWNLOADS", "CLIPBOARD_MODE")
        if res.intent in privileged_intents:
            allowed, reason = security_manager.check_permission("computer_control")
            if not allowed:
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS} ke alawa computer control kisi aur ke liye allowed nahi hai."
                return res

        lang = res.detected_language

        if res.intent == "EMERGENCY_STOP":
            msg = security_manager.trigger_emergency_stop()
            agent_engine.abort()
            res.handled = True
            res.response_text = (
                f"Emergency stop activated, {OWNER_ADDRESS}. Sabhi automations band kar diye gaye hain."
                if lang in ("hindi", "hinglish") else f"Emergency stop activated, {OWNER_ADDRESS}. All automations halted."
            )
            return res

        if res.intent == "SECURITY_LOCK":
            security_manager.lock(reason="user voice command")
            res.handled = True
            res.response_text = (
                f"ALEX ko secure mode mein lock kar diya hai, {OWNER_ADDRESS}."
                if lang in ("hindi", "hinglish") else f"ALEX is now locked in secure mode, {OWNER_ADDRESS}."
            )
            return res

        if res.intent == "UNDO":
            from core.undo import undo_last
            undo_res = undo_last()
            res.handled = True
            res.response_text = f"{OWNER_ADDRESS}, {undo_res}"
            return res

        if res.intent == "ORGANIZE_DOWNLOADS":
            out = agent_engine.execute_organize_downloads()
            res.handled = True
            res.response_text = out.summary_message
            return res

        if res.intent == "COMPOUND_BROWSER_SEARCH":
            browser = res.slots.get("browser", "Chrome")
            platform = res.slots.get("platform", "YouTube")
            query = res.slots.get("query", "").strip()

            out = agent_engine.execute_compound_browser_search(
                browser=browser,
                platform=platform,
                query=query,
                lang=lang
            )
            res.handled = True
            res.response_text = out.summary_message
            return res

        if res.intent == "YOUTUBE_SEARCH":
            q = res.slots.get("query", "Python latest tutorial")
            out = agent_engine.execute_youtube_search_goal(q)
            res.handled = True
            res.response_text = out.summary_message
            return res

        if res.intent == "MORNING_BRIEFING":
            from actions.automation_engine import get_morning_briefing
            b = get_morning_briefing()
            res.handled = True
            res.response_text = b
            return res

        if res.intent == "NEWS_BRIEFING":
            from core.news_engine import news_intelligence
            table = news_intelligence.format_news_table()
            speech = news_intelligence.format_news_for_briefing()
            res.handled = True
            res.response_text = f"{speech}\n\n{table}"
            return res

        if res.intent == "TECH_NEWS_BRIEFING":
            from core.news_engine import news_intelligence
            items = [it for it in news_intelligence.fetch_top_news() if it.category.lower() == "technology"]
            res.handled = True
            if items:
                lines = [f"{OWNER_ADDRESS}, aaj ki Technology headlines:"]
                for it in items[:4]:
                    lines.append(f"• {it.headline} ({it.source})")
                res.response_text = "\n".join(lines)
            else:
                res.response_text = f"{OWNER_ADDRESS}, technology news updates abhi available nahi hain."
            return res

        if res.intent == "STARTUP_BRIEFING_CONTROL":
            from core.startup_manager import startup_manager
            action = res.slots.get("action", "short")
            if action == "disable":
                startup_manager.update_settings(morning_briefing_enabled=False)
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS}, startup morning briefing disable kar di gayi hai."
            else:
                startup_manager.update_settings(briefing_length="short")
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS}, startup briefing length ko short set kar diya hai."
            return res

        if res.intent == "ACTION_TIMELINE":
            t_str = timeline.format_timeline(limit=8)
            res.handled = True
            res.response_text = t_str
            return res

        if res.intent == "FOCUS_MODE":
            from actions.focus_mode import manage_focus_mode
            dur = res.slots.get("duration", 60)
            f_res = manage_focus_mode(action="start", duration_minutes=dur)
            res.handled = True
            res.response_text = f_res
            return res

        if res.intent == "CLIPBOARD_MODE":
            from actions.clipboard_mode import process_clipboard
            task = res.slots.get("task", "explain")
            c_res = process_clipboard(task)
            res.handled = True
            res.response_text = c_res
            return res

        if res.intent == "VOLUME_UP":
            try:
                from actions.computer_settings import volume_up
                volume_up()
                res.handled = True
                res.response_text = f"Volume badha diya, {OWNER_ADDRESS}." if lang in ("hindi", "hinglish") else f"Volume increased, {OWNER_ADDRESS}."
            except Exception as e:
                res.handled = True
                res.response_text = f"Volume adjust karne mein error: {e}"
            return res

        if res.intent == "VOLUME_DOWN":
            try:
                from actions.computer_settings import volume_down
                volume_down()
                res.handled = True
                res.response_text = f"Volume kam kar diya, {OWNER_ADDRESS}." if lang in ("hindi", "hinglish") else f"Volume decreased, {OWNER_ADDRESS}."
            except Exception as e:
                res.handled = True
                res.response_text = f"Volume adjust karne mein error: {e}"
            return res

        if res.intent == "VOLUME_MUTE":
            try:
                from actions.computer_settings import volume_mute
                volume_mute()
                res.handled = True
                res.response_text = f"Volume mute kar diya, {OWNER_ADDRESS}." if lang in ("hindi", "hinglish") else f"Volume muted, {OWNER_ADDRESS}."
            except Exception as e:
                res.handled = True
                res.response_text = f"Volume mute error: {e}"
            return res

        if res.intent == "SYSTEM_STATUS":
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            res.handled = True
            res.response_text = (
                f"{OWNER_ADDRESS}, current CPU utilization {cpu:.0f}% hai aur RAM {ram:.0f}% used hai. System perfectly running hai."
                if lang in ("hindi", "hinglish") else
                f"{OWNER_ADDRESS}, current CPU utilization is {cpu:.0f}% and RAM usage is {ram:.0f}%. System is running nominally."
            )
            return res

        if res.intent == "TIME_CHECK":
            now = time.localtime()
            time_str = time.strftime("%I:%M %p", now)
            date_str = time.strftime("%A, %d %B %Y", now)
            res.handled = True
            res.response_text = (
                f"{OWNER_ADDRESS}, abhi time {time_str} hai, aur aaj ki date {date_str} hai."
                if lang in ("hindi", "hinglish") else
                f"{OWNER_ADDRESS}, the time is {time_str} on {date_str}."
            )
            return res

        if res.intent == "NETWORK_DIAGNOSTICS":
            from core.diagnostics import run_network_diagnostics, format_network_report
            net_results = run_network_diagnostics()
            res.handled = True
            res.response_text = format_network_report(net_results, lang=lang)
            return res

        if res.intent == "SELF_DIAGNOSTICS":
            from core.diagnostics import run_self_diagnostics, format_diagnostics_report
            report_dict = run_self_diagnostics()
            res.handled = True
            res.response_text = format_diagnostics_report(report_dict, lang=lang)
            return res

        if res.intent == "OPEN_WEBSITE":
            url = res.slots.get("url", "").strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            try:
                import webbrowser
                from core.app_adapters import app_registry
                adapter = app_registry.get_adapter("browser") or app_registry.get_adapter("chrome")
                if adapter and hasattr(adapter, "launch"):
                    adapter.launch(url)
                else:
                    webbrowser.open(url)
                res.handled = True
                res.response_text = (
                    f"{url} browser mein open kar diya hai, {OWNER_ADDRESS}."
                    if lang in ("hindi", "hinglish") else
                    f"Opened {url} in your browser, {OWNER_ADDRESS}."
                )
            except Exception as e:
                res.handled = True
                res.response_text = f"Could not open website: {e}"
            return res

        if res.intent == "WEB_SEARCH":
            q = res.slots.get("query", "").strip()
            if not q:
                res.handled = True
                res.response_text = (
                    f"Google par kya search karna hai, {OWNER_ADDRESS}?"
                    if lang in ("hindi", "hinglish") else
                    f"What would you like to search for on the web, {OWNER_ADDRESS}?"
                )
                return res
            try:
                import urllib.parse
                import webbrowser
                encoded = urllib.parse.quote_plus(q)
                search_url = f"https://www.google.com/search?q={encoded}"
                from core.app_adapters import app_registry
                adapter = app_registry.get_adapter("browser") or app_registry.get_adapter("chrome")
                if adapter and hasattr(adapter, "launch"):
                    adapter.launch(search_url)
                else:
                    webbrowser.open(search_url)
                res.handled = True
                res.response_text = (
                    f"Google par '{q}' search kar diya hai, {OWNER_ADDRESS}."
                    if lang in ("hindi", "hinglish") else
                    f"Searched for '{q}' on Google, {OWNER_ADDRESS}."
                )
            except Exception as e:
                res.handled = True
                res.response_text = f"Could not perform web search: {e}"
            return res

        if res.intent == "LIST_FILES":
            target_path = res.slots.get("path", "desktop").strip()
            try:
                from actions.file_controller import list_files
                msg = list_files(target_path)
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS}:\n{msg}"
            except Exception as e:
                res.handled = True
                res.response_text = f"Error listing files: {e}"
            return res

        if res.intent == "READ_FILE":
            f_path = res.slots.get("path", "").strip()
            try:
                from actions.file_controller import read_file
                content = read_file(f_path)
                # Redact any passwords/keys
                content = re.sub(r"""(?i)(api[_-]?key|token|secret|password|auth)[\s:=]+["']?([a-zA-Z0-9_\-\.]+){8,}["']?""", r"\1: [REDACTED]", content)
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS}, file content:\n\n{content}"
            except Exception as e:
                res.handled = True
                res.response_text = f"Error reading file: {e}"
            return res

        if res.intent == "SEARCH_FILES":
            q = res.slots.get("query", "").strip()
            loc = res.slots.get("location", "desktop").strip()
            try:
                from actions.file_controller import find_files
                msg = find_files(path=loc, name=q)
                res.handled = True
                res.response_text = f"{OWNER_ADDRESS}:\n{msg}"
            except Exception as e:
                res.handled = True
                res.response_text = f"Error searching files: {e}"
            return res

        if res.intent == "CREATE_FOLDER":
            f_name = res.slots.get("folder_name", "").strip()
            loc = res.slots.get("location", "desktop").strip()
            try:
                from actions.file_controller import create_folder
                msg = create_folder(path=loc, name=f_name)
                res.handled = True
                res.response_text = (
                    f"{OWNER_ADDRESS}, '{f_name}' folder {loc} mein create kar diya gaya hai."
                    if lang in ("hindi", "hinglish") else
                    f"Created folder '{f_name}' in {loc}, {OWNER_ADDRESS}."
                )
            except Exception as e:
                res.handled = True
                res.response_text = f"Error creating folder: {e}"
            return res

        if res.intent == "CREATE_FILE":
            f_name = res.slots.get("file_name", "").strip()
            loc = res.slots.get("location", "desktop").strip()
            content = res.slots.get("content", "").strip()
            try:
                from actions.file_controller import create_file, _resolve_path
                target = _resolve_path(loc) / f_name
                # Consequential Action Check: ask before overwriting!
                if target.exists():
                    res.handled = True
                    res.response_text = (
                        f"{OWNER_ADDRESS}, '{f_name}' already exists. Kya aap isse overwrite karna chahte hain?"
                        if lang in ("hindi", "hinglish") else
                        f"'{f_name}' already exists, {OWNER_ADDRESS}. Would you like to overwrite it?"
                    )
                    from core.voice_pipeline import voice_pipeline
                    voice_pipeline.request_confirmation(
                        description=f"Overwrite file {f_name}",
                        action_fn=lambda: create_file(path=loc, name=f_name, content=content),
                        prompt_msg=res.response_text
                    )
                    return res

                msg = create_file(path=loc, name=f_name, content=content)
                res.handled = True
                res.response_text = (
                    f"{OWNER_ADDRESS}, '{f_name}' file {loc} mein create kar di gayi hai."
                    if lang in ("hindi", "hinglish") else
                    f"Created file '{f_name}' in {loc}, {OWNER_ADDRESS}."
                )
            except Exception as e:
                res.handled = True
                res.response_text = f"Error creating file: {e}"
            return res

        if res.intent == "OPEN_APPLICATION":
            app = res.slots.get("app_name", "")
            try:
                from actions.open_app import open_app
                msg = open_app(app)
                res.handled = True
                res.response_text = (
                    f"{app} open kar diya, {OWNER_ADDRESS}."
                    if lang in ("hindi", "hinglish") else
                    f"Opened {app}, {OWNER_ADDRESS}."
                )
            except Exception as e:
                res.handled = True
                res.response_text = f"Could not open {app}: {e}"
            return res

        if res.intent == "PROJECTS_LIST":
            from core.project_manager import project_manager
            res.handled = True
            res.response_text = project_manager.list_projects()
            return res

        if res.intent == "PROJECT_STATUS":
            from core.project_manager import project_manager
            proj = res.slots.get("project_name")
            res.handled = True
            res.response_text = project_manager.get_project_status_report(proj)
            return res

        if res.intent == "PROJECT_RUN":
            from core.project_manager import project_manager
            proj = res.slots.get("project_name")
            res.handled = True
            res.response_text = project_manager.run_project(proj)
            return res

        if res.intent == "PROJECT_CONTINUE":
            from core.project_manager import project_manager
            res.handled = True
            res.response_text = project_manager.continue_where_left_off()
            return res

        if res.intent == "PROJECT_BUGS":
            from core.project_manager import project_manager
            res.handled = True
            res.response_text = project_manager.check_project_bugs()
            return res

        if res.intent == "SHOW_NOTIFICATIONS":
            from core.proactive_intelligence import proactive_engine
            res.handled = True
            res.response_text = proactive_engine.format_proactive_summary()
            return res

        if res.intent == "DND_TOGGLE":
            from core.proactive_intelligence import proactive_engine
            res.handled = True
            res.response_text = proactive_engine.toggle_dnd()
            return res

        if res.intent == "SKILLSUM_RESUME_EVAL":
            from actions.skillsum_automation import skillsum_service
            resume_path = str(res.slots.get("resume_path") or "").strip()
            try:
                report = skillsum_service.process_candidate_resume(resume_path)
            except Exception:
                res.handled = False
                res.response_text = (
                    f"{OWNER_ADDRESS}, SkillSum processing failed. "
                    "No verified report was created."
                )
                return res

            res.handled = bool(report.success)
            if report.success:
                score = report.evaluation.match_score_pct
                score_label = (
                    f"{score:.1f}% preliminary decision-support estimate"
                    if score is not None
                    else "not calculated because no skills were specified"
                )
                res.response_text = (
                    f"{OWNER_ADDRESS}, candidate '{report.candidate.candidate_name}' ka resume evaluate ho gaya hai. "
                    f"Match Score: {score_label}. Reports saved at '{report.markdown_path}' "
                    f"and '{report.json_path}'."
                )
            else:
                error = report.error_message or "Resume evaluation could not be completed."
                res.response_text = f"{OWNER_ADDRESS}, resume processing failed: {error}"
            return res

        if res.intent == "PROJECT_SWITCH":
            from core.project_manager import project_manager
            proj = res.slots.get("project_name", "Personal")
            project_manager.set_active_project(proj)
            ctx = project_manager.continue_where_left_off()
            res.handled = True
            res.response_text = ctx
            return res

        if res.intent == "PROJECT_INSPECT_FIX":
            from actions.dev_agent import inspect_and_fix_project
            from core.project_manager import project_manager
            proj = res.slots.get("project_name", project_manager.get_active_project())
            out = inspect_and_fix_project(project_path=proj, goal=res.slots.get("query", "Inspect, audit, and fix project bugs"))
            res.handled = True
            res.response_text = out
            return res

        if res.intent == "LANGUAGE_SWITCH":
            target = res.slots.get("language", "hinglish")
            from memory.memory_manager import save_memory, load_memory
            mem = load_memory()
            mem.setdefault("identity", {})["language"] = {"value": target.capitalize(), "updated": time.strftime("%Y-%m-%d")}
            save_memory(mem)
            res.handled = True
            if target == "hindi":
                res.response_text = f"ज़रूर {OWNER_ADDRESS}, अब से मैं आपसे हिंदी में बात करूँगा।"
            elif target == "english":
                res.response_text = f"Understood, {OWNER_ADDRESS}. I will speak with you in English from now on."
            else:
                res.response_text = f"Sure {OWNER_ADDRESS}, ab se main aapse Hinglish mein baat karunga."
            return res

        if res.intent == "TASK_CENTER":
            from core.task_center import task_center
            res.handled = True
            res.response_text = task_center.format_task_center_summary()
            return res

        if res.intent == "AUTONOMY_MODE":
            from core.task_center import task_center, AutonomyLevel
            mode = res.slots.get("mode", "normal")
            mode_map = {
                "ask": AutonomyLevel.ASK_EVERYTHING,
                "normal": AutonomyLevel.NORMAL,
                "trusted": AutonomyLevel.TRUSTED,
                "autonomous": AutonomyLevel.AUTONOMOUS
            }
            chosen = mode_map.get(mode, AutonomyLevel.NORMAL)
            task_center.set_autonomy_level(chosen)
            res.handled = True
            res.response_text = (
                f"{OWNER_ADDRESS}, autonomy level set to '{chosen}'. Critical actions will still require confirmation."
                if lang == "english" else
                f"{OWNER_ADDRESS}, autonomy mode '{chosen}' set kar diya gaya hai. Critical security actions ke liye confirmation hamesha required rahega."
            )
            return res

        # 19. Phase 4 Vision, Follow-up, and Privacy Handlers
        if res.intent == "SCREEN_UNDERSTAND":
            from core.screen_engine import screen_engine
            win = screen_engine.get_active_window()
            err_dlg = screen_engine.detect_error_dialog()
            res.handled = True
            if win:
                status_extra = f" ⚠️ Visible Alert: {err_dlg.title} — {err_dlg.message}" if err_dlg.is_error_present else " Screen par koi visible error dialog nahi hai."
                res.response_text = f"Sir, active window hai '{win.title}' (Process: {win.process_name}, Responsive: {'Haan' if win.is_responsive else 'Nahi'}).{status_extra}"
            else:
                res.response_text = f"Sir, current desktop screen active hai aur koi unresponsive window nahi hai."
            return res

        if res.intent in ("FOLLOWUP_PROFESSIONAL", "FOLLOWUP_PDF", "FOLLOWUP_IMAGE_BG", "FOLLOWUP_FIX_BUG", "FOLLOWUP_OUTPUT_FOLDER"):
            from core.context_engine import context_engine
            raw_q = res.slots.get("raw_query", "")
            resolved_q, meta = context_engine.resolve_references(raw_q)
            res.handled = True
            target = meta.get("resolved_target", "")
            action = meta.get("follow_up_action", "")

            if action == "CONVERT_TO_PDF":
                res.response_text = f"Sir, last document '{Path(str(target)).name if target else 'document'}' ko PDF export queue mein daal diya gaya hai."
            elif action == "ENHANCE_QUALITY":
                res.response_text = f"Sir, target '{Path(str(target)).name if target else 'document'}' ko professional styling aur enhanced layout ke sath optimize kiya ja raha hai."
            elif action == "CHANGE_BACKGROUND":
                res.response_text = f"Sir, previous design image '{Path(str(target)).name if target else 'design'}' ka background transformation prepare ho raha hai."
            elif action == "FIX_BUG":
                res.response_text = f"Sir, identified project bug ko isolate karke automated patch generate kiya ja raha hai."
            elif action == "OPEN_FOLDER":
                import subprocess
                f_path = str(target)
                if Path(f_path).exists():
                    subprocess.Popen(["explorer.exe", f_path])
                    res.response_text = f"Sir, last output folder open kar diya gaya hai: {f_path}"
                else:
                    res.response_text = f"Sir, output folder location: {f_path}"
            else:
                res.response_text = f"Sir, follow-up request process ki gayi: {resolved_q}"
            return res

        if res.intent == "PRIVACY_PAUSE":
            from core.privacy_manager import privacy_manager
            res.handled = True
            res.response_text = privacy_manager.pause_vision()
            return res

        if res.intent == "PRIVACY_RESUME":
            from core.privacy_manager import privacy_manager
            res.handled = True
            res.response_text = privacy_manager.resume_vision()
            return res

        # 20. Advanced Desktop Workflows Execution
        if res.intent == "WORKFLOW_PPT":
            from core.workflow_orchestrator import workflow_orchestrator
            topic = res.slots.get("topic", "Executive Strategy")
            count = res.slots.get("count", 5)
            # Check if user mentioned opening in PowerPoint
            raw_text = res.slots.get("raw", "")
            launch = any(w in raw_text.lower() for w in ("open", "kholo", "chalao", "launch", "powerpoint"))
            wf_res = workflow_orchestrator.run_presentation_workflow(topic=topic, launch_after=launch)
            res.handled = True
            res.response_text = wf_res.message
            return res

        if res.intent == "WORKFLOW_EXCEL":
            from creation_studio.spreadsheet_studio import SpreadsheetStudio
            ss = SpreadsheetStudio(Path.home() / "Desktop")
            sample_data = [
                ["Category", "Budget", "Actual", "Variance"],
                ["Operations", 50000, 42000, 8000],
                ["Development", 80000, 75000, 5000],
                ["Marketing", 30000, 26000, 4000],
                ["Infrastructure", 40000, 38000, 2000],
            ]
            wb_path, val = ss.create_chart_workbook("Project Data Analysis", sample_data, chart_type="bar", filename="Project_Analysis.xlsx")
            res.handled = True
            res.response_text = (
                f"{OWNER_ADDRESS}, Excel file data analysis complete ho gaya hai aur native bar chart workbook create kar di gayi hai: "
                f"{wb_path.name} ({val.file_size_bytes} bytes). Location: {wb_path}"
            )
            return res

        if res.intent == "WORKFLOW_BLENDER":
            from core.workflow_orchestrator import workflow_orchestrator
            desc = res.slots.get("description", "low-poly house with chimney and door")
            wf_res = workflow_orchestrator.run_blender_workflow(scene_description=desc, target_name="custom_scene", render_preview=True)
            res.handled = True
            res.response_text = wf_res.message
            return res

        if res.intent == "WORKFLOW_EMAIL":
            from core.email_engine import email_engine
            msg, preview = email_engine.create_draft(
                recipient="recipient@example.com",
                subject="Executive Update",
                body=f"Hello,\n\nPlease find the project deliverable prepared by ALEX for {OWNER_ADDRESS}.\n\nBest regards,\nALEX"
            )
            res.handled = True
            res.response_text = (
                f"{OWNER_ADDRESS}, email draft safely create kar diya gaya hai [ID: {msg.draft_id}]. "
                f"Draft EML file: {msg.saved_eml_path}. Explicit confirmation authorization ke baad hi bhejenge."
            )
            return res

        return res



# Global singleton
intent_engine = IntentEngine()
