"""
workflow/planner.py — Goal Deconstruction, Task Planning & DAG Dependency Engine.

Deconstructs natural language user requests (Hindi, Hinglish, English) into
structured, verifiable, directed acyclic graph (DAG) execution steps.

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from workflow.models import TaskStatus, Workflow, WorkflowStatus, WorkflowTask


class WorkflowPlanner:
    """Deconstructs user goals into structured, verifiable task DAGs."""

    @staticmethod
    def generate_workflow_id() -> str:
        return f"WF-{int(time.time() * 1000) % 1000000:06d}"

    @staticmethod
    def validate_dag(tasks: List[WorkflowTask]) -> Tuple[bool, str]:
        """
        Validates that tasks form a valid Directed Acyclic Graph (DAG) with no cycles
        and all dependencies exist.
        """
        task_ids = {t.task_id for t in tasks}
        # Check all declared dependencies exist
        for t in tasks:
            for dep in t.dependencies:
                if dep not in task_ids:
                    return False, f"Task '{t.task_id}' depends on non-existent task '{dep}'."
                if dep == t.task_id:
                    return False, f"Task '{t.task_id}' cannot depend on itself."

        # Cycle detection via DFS
        adj: Dict[str, List[str]] = {t.task_id: list(t.dependencies) for t in tasks}
        visited: Dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited

        def _dfs(node: str) -> bool:
            visited[node] = 1
            for pre in adj.get(node, []):
                if visited.get(pre, 0) == 1:
                    return True  # Cycle detected
                if visited.get(pre, 0) == 0:
                    if _dfs(pre):
                        return True
            visited[node] = 2
            return False

        for t in tasks:
            if visited.get(t.task_id, 0) == 0:
                if _dfs(t.task_id):
                    return False, f"Circular dependency detected involving task '{t.task_id}'."

        return True, "Valid DAG."

    @staticmethod
    def get_topological_order(tasks: List[WorkflowTask]) -> List[WorkflowTask]:
        """Returns tasks ordered such that all dependencies appear before dependents."""
        task_map = {t.task_id: t for t in tasks}
        in_degree = {t.task_id: len(t.dependencies) for t in tasks}
        dependents: Dict[str, List[str]] = {t.task_id: [] for t in tasks}

        for t in tasks:
            for dep in t.dependencies:
                if dep in dependents:
                    dependents[dep].append(t.task_id)

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        sorted_ids = []

        while queue:
            curr = queue.pop(0)
            sorted_ids.append(curr)
            for dep_id in dependents.get(curr, []):
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        return [task_map[tid] for tid in sorted_ids if tid in task_map]

    def plan_workflow(self, request_text: str, project_id: Optional[str] = None) -> Workflow:
        """
        Analyzes natural language request and creates structured workflow with DAG tasks.
        """
        wf_id = self.generate_workflow_id()
        q = request_text.lower().strip()
        tasks: List[WorkflowTask] = []
        desired_outcome = ""

        # ── Template 1: Python Project Bug Finding, Fixing & Test Execution ───
        if ("bug" in q or "fix" in q or "test" in q) and ("project" in q or "python" in q or "code" in q):
            proj = project_id or "SkillSum"
            desired_outcome = f"Discover, repair, and verify bugs in project '{proj}' with automated test execution."
            t1 = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective=f"Scan project '{proj}' for syntax anomalies, AST violations, and unresolved bugs",
                inputs={"project": proj, "scope": "full_ast"},
                expected_output="Detailed inventory of syntax or logical defects",
                required_skill="code_helper",
                action_name="code_helper",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2 = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective=f"Apply targeted patches to resolve detected defects in '{proj}'",
                inputs={"project": proj, "auto_commit": False},
                expected_output="Patched files with clean AST parse",
                required_skill="dev_agent",
                action_name="dev_agent",
                dependencies=[t1.task_id],
                permission_requirements=2,
                verification_procedure="syntax_valid",
                recovery_strategy="rollback"
            )
            t3 = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective=f"Execute regression test suites for '{proj}' to verify patch integrity",
                inputs={"project": proj, "run_tests": True},
                expected_output="Test execution report with pass/fail counts",
                required_skill="dev_agent",
                action_name="dev_agent",
                dependencies=[t2.task_id],
                permission_requirements=2,
                verification_procedure="test_suite"
            )
            t4 = WorkflowTask(
                task_id=f"{wf_id}-T4",
                objective=f"Compile final bug repair report and update project memory for '{proj}'",
                inputs={"project": proj, "goal": desired_outcome},
                expected_output="Final verification summary record",
                required_skill="knowledge_brain",
                action_name="knowledge_brain",
                dependencies=[t3.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1, t2, t3, t4]

        # ── Template 2: PDF to Presentation Generation & Validation ───────────
        elif ("pdf" in q or "document" in q) and ("presentation" in q or "pptx" in q or "slides" in q):
            desired_outcome = "Ingest source PDF, extract structured slide deck, and generate validated PPTX."
            t1 = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective="Ingest source PDF and extract structured outlines, headers, and bullet points",
                inputs={"format": "pdf", "action": "extract_outline"},
                expected_output="Structured presentation outline JSON",
                required_skill="file_processor",
                action_name="file_processor",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2 = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective="Generate professional widescreen PowerPoint presentation (PPTX)",
                inputs={"title": "Executive Presentation", "format": "pptx"},
                expected_output="Generated presentation file on disk",
                required_skill="document_creator",
                action_name="create_document",
                dependencies=[t1.task_id],
                permission_requirements=2,
                verification_procedure="file_exists",
                recovery_strategy="retry_exponential"
            )
            t3 = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective="Inspect and validate generated PPTX file structure, readability, and slide count",
                inputs={"verify_file": True},
                expected_output="File verification report with positive integrity check",
                required_skill="file_processor",
                action_name="file_processor",
                dependencies=[t2.task_id],
                permission_requirements=1,
                verification_procedure="file_exists"
            )
            t4 = WorkflowTask(
                task_id=f"{wf_id}-T4",
                objective="Register validated presentation artifact into knowledge library",
                inputs={"category": "artifacts"},
                expected_output="Stored artifact metadata",
                required_skill="knowledge_brain",
                action_name="knowledge_brain",
                dependencies=[t3.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1, t2, t3, t4]

        # ── Template 3: Project Comprehensive Audit & Security Report ─────────
        elif "audit" in q and ("security" in q or "feature" in q or "report" in q or "missing" in q):
            proj = project_id or "SkillSum"
            desired_outcome = f"Perform complete codebase audit, security vulnerability scan, and generate audit report for '{proj}'."
            # Parallel branch: Code audit and Security audit run independently
            t1_code = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective=f"Audit repository architecture, Git status, and feature completion in '{proj}'",
                inputs={"project": proj, "scope": "architecture"},
                expected_output="Codebase feature completeness audit",
                required_skill="dev_agent",
                action_name="dev_agent",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2_sec = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective=f"Scan for exposed credentials, secret leakage, and permission vulnerabilities in '{proj}'",
                inputs={"project": proj, "scope": "security"},
                expected_output="Security vulnerability assessment findings",
                required_skill="system_monitor",
                action_name="get_system_status",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t3_combine = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective=f"Synthesize architectural audit and security scan findings into unified audit document",
                inputs={"project": proj, "document_type": "audit_report"},
                expected_output="Generated executive audit document file",
                required_skill="document_creator",
                action_name="create_document",
                dependencies=[t1_code.task_id, t2_sec.task_id],
                permission_requirements=2,
                verification_procedure="file_exists"
            )
            t4_verify = WorkflowTask(
                task_id=f"{wf_id}-T4",
                objective="Verify generated audit report readability and record in project memory",
                inputs={"project": proj},
                expected_output="Verified audit report recorded in SQLite memory",
                required_skill="knowledge_brain",
                action_name="knowledge_brain",
                dependencies=[t3_combine.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1_code, t2_sec, t3_combine, t4_verify]

        # ── Template 4: Research, Synthesis & PDF Document Save ───────────────
        elif "research" in q and ("pdf" in q or "report" in q or "save" in q):
            desired_outcome = "Conduct deep multi-source research, synthesize factual citations, and generate PDF report."
            t1 = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective="Conduct multi-source web discovery and extract verified factual citations",
                inputs={"topic": request_text, "max_sources": 3},
                expected_output="Verified research citations and structured notes",
                required_skill="deep_research",
                action_name="deep_research",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2 = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective="Synthesize research findings into formatted executive document",
                inputs={"title": "Research Synthesis Report", "format": "pdf"},
                expected_output="Generated research PDF document on disk",
                required_skill="document_creator",
                action_name="create_document",
                dependencies=[t1.task_id],
                permission_requirements=2,
                verification_procedure="file_exists"
            )
            t3 = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective="Verify generated PDF integrity, non-zero file size, and readable structure",
                inputs={"verify_file": True},
                expected_output="File integrity confirmation",
                required_skill="file_processor",
                action_name="file_processor",
                dependencies=[t2.task_id],
                permission_requirements=1,
                verification_procedure="file_exists"
            )
            t4 = WorkflowTask(
                task_id=f"{wf_id}-T4",
                objective="Index research findings and PDF citation records into Knowledge Brain",
                inputs={"category": "research"},
                expected_output="FTS5 indexed knowledge entry",
                required_skill="knowledge_brain",
                action_name="knowledge_brain",
                dependencies=[t3.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1, t2, t3, t4]

        # ── Template 5: VS Code Launch & Development Workspace Setup ──────────
        elif ("vscode" in q or "vs code" in q or "code" in q) and ("open" in q or "kholo" in q or "start" in q):
            proj = project_id or "SkillSum"
            desired_outcome = f"Verify project '{proj}' workspace and launch VS Code development environment."
            t1 = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective=f"Verify project directory, Git status, and virtual environment for '{proj}'",
                inputs={"project": proj},
                expected_output="Verified workspace path and clean environment checks",
                required_skill="dev_agent",
                action_name="dev_agent",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2 = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective=f"Launch Visual Studio Code in project workspace '{proj}'",
                inputs={"app_name": "code", "target": proj},
                expected_output="Launched editor process",
                required_skill="computer_control",
                action_name="open_app",
                dependencies=[t1.task_id],
                permission_requirements=2,
                verification_procedure="output_non_empty"
            )
            t3 = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective="Observe desktop screen to verify VS Code window focus and workspace load",
                inputs={"app_name": "code"},
                expected_output="Confirmed active editor window",
                required_skill="system_monitor",
                action_name="get_system_status",
                dependencies=[t2.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1, t2, t3]

        # ── Fallback Template: General Multi-Step Goal Deconstruction ─────────
        else:
            desired_outcome = f"Safely execute and verify requested multi-step task: '{request_text}'"
            t1 = WorkflowTask(
                task_id=f"{wf_id}-T1",
                objective=f"Analyze requirements, dependencies, and parameters for '{request_text}'",
                inputs={"goal": request_text},
                expected_output="Validated operational parameters",
                required_skill="system_monitor",
                action_name="get_system_status",
                dependencies=[],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            t2 = WorkflowTask(
                task_id=f"{wf_id}-T2",
                objective=f"Execute primary operations for '{request_text}'",
                inputs={"goal": request_text},
                expected_output="Execution results",
                required_skill="automation_engine",
                action_name="automation_engine",
                dependencies=[t1.task_id],
                permission_requirements=2,
                verification_procedure="output_non_empty"
            )
            t3 = WorkflowTask(
                task_id=f"{wf_id}-T3",
                objective=f"Verify execution outcome and record summary for Aditya Sir",
                inputs={"goal": request_text},
                expected_output="Verified completion telemetry",
                required_skill="knowledge_brain",
                action_name="knowledge_brain",
                dependencies=[t2.task_id],
                permission_requirements=1,
                verification_procedure="output_non_empty"
            )
            tasks = [t1, t2, t3]

        # Validate DAG structure
        is_dag, dag_err = self.validate_dag(tasks)
        if not is_dag:
            raise ValueError(f"Internal planning error creating DAG: {dag_err}")

        wf = Workflow(
            workflow_id=wf_id,
            user_request=request_text,
            desired_outcome=desired_outcome,
            current_status=WorkflowStatus.READY,
            tasks=tasks,
            project_id=project_id
        )
        return wf


# Singleton Instance
workflow_planner = WorkflowPlanner()
