# ALEX Skills Engine & Plugin Developer Guide (Phase 7)

**Owner:** Aditya Rajak  
**Preferred Salutation:** Aditya Sir / Sir  
**Assistant:** ALEX  
**Platform:** Windows Desktop / Cross-Platform  

---

## 1. System Overview

ALEX 7.0 features a unified, sandboxed, and security-governed **Skills Engine** designed to host both built-in core actions and extensible user plugins. Every capability runs under strict execution guarantees:

1. **Centralized Discovery & Registration:** Discovers built-in capabilities and plugins dynamically from `actions/` and `plugins/`.
2. **Standard Execution Contract:** No skill executes without parameter validation, Central Security Manager authorization, dependency audits, isolated sandboxing, and outcome verification.
3. **AST-Driven Security Verification:** Third-party plugins are statically audited using Python AST and heuristic scanners to reject hostile code (such as shadow-copy tampering, UAC bypasses, destructive file deletes, or unauthorized process spawning).
4. **Crash Containment:** Runs in an isolated thread worker sandbox with timeout enforcement, capturing standard streams and preventing faulty plugins from terminating ALEX.

---

## 2. The 6 Core Skill Categories

All skills and plugins belong to one of the following official categories:

| Category | Enum | Purpose & Scope |
| :--- | :--- | :--- |
| **Computer and Desktop** | `SkillCategory.COMPUTER_DESKTOP` | Mouse, keyboard, active application manipulation, window focus, volume, and display control. |
| **Browser and Web** | `SkillCategory.BROWSER_WEB` | Automated web navigation, search queries, DOM interaction, page extraction, and web research. |
| **Documents and Creativity** | `SkillCategory.DOCUMENTS_CREATIVITY` | PDF, DOCX, XLSX analysis, document summarization, report authoring, and presentation generation. |
| **Development** | `SkillCategory.DEVELOPMENT` | Project repository management, AST code linting, bug repair, Git automation, and test runner. |
| **Personal Productivity** | `SkillCategory.PERSONAL_PRODUCTIVITY` | Multi-layer memory indexing, personal knowledge brain, reminders, schedule briefings, and focus routines. |
| **System Intelligence** | `SkillCategory.SYSTEM_INTELLIGENCE` | Real-time CPU/RAM/Disk metrics, hardware telemetry, process audits, and self-repair diagnostics. |

---

## 3. Skill Manifest Specification (`SkillManifest`)

Every skill exposes a structured `SkillManifest` declaring its requirements and metadata:

```python
from skills.sdk import SkillManifest, SkillCategory

manifest = SkillManifest(
    skill_id="custom_text_helper",             # Unique ID: 2-64 alphanumeric, dash, or underscore characters
    name="Custom Text Helper",                 # Display name
    description="Transforms and counts words.", # Clear functional description
    version="1.0.0",                           # Semantic version string
    author="Aditya Sir",                       # Author / Origin
    category=SkillCategory.DEVELOPMENT,        # One of the 6 official categories
    required_permissions=2,                    # 1=Read, 2=Normal, 3=Sensitive (Approval Required)
    dependencies=["requests"],                 # Required Python modules
    system_binaries=[],                        # Required system executables (e.g. ffmpeg, git)
    supported_os=["windows", "linux"],         # Supported platforms
    input_schema={                             # JSON Schema for parameters
        "type": "object",
        "properties": {
            "text": {"type": "string"}
        },
        "required": ["text"]
    },
    output_schema={"type": "object"},          # Expected output schema
    timeout_seconds=30,                        # Max execution time before automatic cancellation
    is_sandboxed=True,                         # Thread/Process sandbox isolation
    tags=["text", "utility"]                   # Tags for discovery & planner routing
)
```

### Permission Tiers

| Level | Name | Clearance Rule |
| :---: | :--- | :--- |
| **1** | **Read-Only** | Telemetry, file inspection, read-only queries. Auto-approved. |
| **2** | **Normal** | Safe file edits, standard calculations, browser read navigation. Auto-approved for verified owner. |
| **3** | **Sensitive** | Writing executable scripts, modifying system configurations, bulk file moves. Requires explicit confirmation (`__confirmed__=True`). |
| **4** | **Restricted** | System registry tampering, disk wiping, raw security bypass. Permanently prohibited. |

---

## 4. Developing a Skill with `BaseAlexSkill`

Create a subclass of `BaseAlexSkill` in `plugins/<plugin_name>.py`:

```python
from typing import Dict, Any, Optional
from skills.sdk import BaseAlexSkill, SkillManifest, SkillCategory, SkillContext

class MyCustomSkill(BaseAlexSkill):
    def __init__(self):
        manifest = SkillManifest(
            skill_id="my_custom_skill",
            name="My Custom Skill",
            description="Sample demonstration skill for ALEX",
            category=SkillCategory.PERSONAL_PRODUCTIVITY,
            required_permissions=2,
            dependencies=[]
        )
        super().__init__(manifest)
        self.register_action("greet", self.greet)

    def greet(self, name: str = "Sir", **kwargs) -> str:
        return f"Greetings {name}, ALEX is at your service."

    def run(self, parameters: Dict[str, Any], ctx: Optional[SkillContext] = None) -> Any:
        action = parameters.get("action", "greet")
        if action == "greet":
            return self.greet(name=parameters.get("name", "Sir"))
        return f"Unknown action: {action}"

# Export for automatic discovery
SKILL = MyCustomSkill()
MANIFEST = SKILL.manifest
```

---

## 5. Plugin Security, AST Scanning & Backups

When installing third-party plugins via `PluginInstaller`:

1. **AST & Pattern Inspection:** The code is statically parsed into an AST. Any calls invoking `ctypes`, raw memory manipulation, `vssadmin` deletion, or direct SAM registry access are rejected immediately.
2. **Automated Snapshot Backups:** If a file already exists in `plugins/`, a pre-installation snapshot is stored in `memory/plugin_backups/<plugin_id>/`.
3. **Dry-Run Health Check:** The installer verifies that dependencies and imports can be resolved safely before enabling the plugin.
4. **Instant Rollback:** If a newly installed plugin encounters runtime errors, `plugin_installer.rollback_plugin(plugin_id)` restores the previous snapshot instantly.

---

## 6. Execution Lifecycle & "No False Success"

Execution proceeds through 8 mandatory steps:

```
[1. Validate Inputs]
       ↓
[2. Central Security Clearance] ──(Denied)──> Return ExecutionStatus.FAILED
       ↓
[3. Dependency & Environment Check] ──(Missing)──> Return ExecutionStatus.DEPENDENCY_UNAVAILABLE
       ↓
[4. Consequential Action Check] ──(Level 3 Unconfirmed)──> Return ExecutionStatus.REQUIRES_APPROVAL
       ↓
[5. Sandboxed Thread Execution] ──(Timeout)──> Return ExecutionStatus.CANCELLED
       ↓
[6. Intercept stdout / stderr Streams]
       ↓
[7. Outcome Verification] ──(Output starts with Error/Exception)──> Return ExecutionStatus.FAILED
       ↓
[8. Record Diagnostics & Latency]
```

ALEX never declares an action successful unless the execution handler returns valid output and passes verification.

---

## 7. REST APIs for Skills Management

The ALEX Dashboard server exposes the following endpoints:

- `GET /api/skills/list`: Returns all registered skills with category, status, and metrics.
- `POST /api/skills/{id}/enable`: Enables an installed skill.
- `POST /api/skills/{id}/disable`: Disables an installed skill.
- `GET /api/skills/{id}/health-check`: Runs live dependency and handler diagnostics.
- `POST /api/skills/install`: Safely validates and installs a new plugin code string or file.
- `POST /api/skills/{id}/rollback`: Restores the previous backup snapshot of a plugin.
- `POST /api/skills/execute`: Executes a skill action with input parameters and context.

