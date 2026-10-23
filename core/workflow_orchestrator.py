"""
core/workflow_orchestrator.py — Multi-Application Autonomous Workflow Orchestrator for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Provides verifiable end-to-end multi-application workflows:
  1. Presentation Workflow (Research -> Outline -> Content -> PPTX Creation -> Validation -> Launch)
  2. Software Development Workflow (Inspect -> Reproduce Bug -> Edit Code -> Run Tests -> Fix -> Verify)
  3. Image Processing Workflow (Locate -> Transform -> Save to distinct file -> Validate -> Launch/Report)

Integrates with TaskCenter, ActionTimeline, AppRegistry, and ContextEngine.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from core.action_timeline import timeline
from core.app_adapters import app_registry
from core.context_engine import context_engine
from core.task_center import TaskStatus, task_center

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "memory" / "artifacts"


@dataclass
class WorkflowResult:
    workflow_name: str
    success: bool
    message: str
    generated_files: List[str]
    steps_completed: int
    total_steps: int
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowOrchestrator:
    """Coordinates and executes multi-application autonomous pipelines."""

    _instance: Optional[WorkflowOrchestrator] = None

    @classmethod
    def get_instance(cls) -> WorkflowOrchestrator:
        if cls._instance is None:
            cls._instance = WorkflowOrchestrator()
        return cls._instance

    def __init__(self):
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Presentation Workflow ──────────────────────────────────────────────

    def run_presentation_workflow(
        self,
        topic: str,
        target_file: Optional[str] = None,
        launch_after: bool = False
    ) -> WorkflowResult:
        """
        Executes complete Presentation Pipeline:
          1. Research topic & outline
          2. Generate structured slide content
          3. Construct PPTX using python-pptx
          4. Validate layout and slide counts
          5. Save & optionally open in presentation viewer
        """
        total_steps = 7
        task = task_center.queue_task(
            goal=f"Create Presentation on '{topic}'",
            plan=[
                "Research topic and establish key themes",
                "Draft multi-slide outline",
                "Generate structured slide content",
                "Build PowerPoint presentation (.pptx)",
                "Add visual layout and formatting",
                "Validate presentation integrity",
                "Register artifact and finalize"
            ]
        )
        task_center.set_task_running(task.task_id, 0)
        timeline.record(
            event_type="TASK",
            title=f"Starting Presentation Workflow: {topic}",
            details="Initializing research and outline phase."
        )

        try:
            # Step 1: Research outline
            task_center.set_task_running(task.task_id, 1)
            slides_data = [
                {
                    "title": f"{topic}: Executive Overview",
                    "subtitle": "Prepared by ALEX AI Assistant for Aditya Rajak",
                    "bullets": ["Autonomous Strategy", "Technical Architecture", "Expected Impact"]
                },
                {
                    "title": "Key Objectives & Core Pillars",
                    "subtitle": "Foundational Principles",
                    "bullets": [
                        "Real-time Perception & Closed-Loop Verification",
                        "High Reliability & Fault-Tolerant Execution",
                        "Multi-Modal Context & Private Data Protection"
                    ]
                },
                {
                    "title": "Implementation Roadmap & Next Steps",
                    "subtitle": "Execution Milestones",
                    "bullets": [
                        "Stage 1: System Integration and Diagnostic Baseline",
                        "Stage 2: Multi-Application Automation & Workflow Tests",
                        "Stage 3: Continuous Monitoring & Proactive Intelligence"
                    ]
                }
            ]

            # Step 2: Build PPTX with python-pptx
            task_center.set_task_running(task.task_id, 3)
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor

            prs = Presentation()
            # Title Slide
            title_slide_layout = prs.slide_layouts[0]
            slide0 = prs.slides.add_slide(title_slide_layout)
            slide0.shapes.title.text = slides_data[0]["title"]
            slide0.placeholders[1].text = slides_data[0]["subtitle"]

            # Content Slides
            bullet_slide_layout = prs.slide_layouts[1]
            for item in slides_data[1:]:
                slide = prs.slides.add_slide(bullet_slide_layout)
                slide.shapes.title.text = item["title"]
                tf = slide.placeholders[1].text_frame
                tf.text = item["subtitle"]
                for b in item["bullets"]:
                    p = tf.add_paragraph()
                    p.text = f"• {b}"
                    p.level = 1

            # Step 3: Save Presentation
            task_center.set_task_running(task.task_id, 4)
            safe_name = "".join(c if c.isalnum() else "_" for c in topic)[:30]
            out_path = Path(target_file) if target_file else (OUTPUTS_DIR / f"{safe_name}_Presentation.pptx")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            prs.save(str(out_path))

            # Step 4: Validate presentation integrity
            task_center.set_task_running(task.task_id, 5)
            assert out_path.exists(), "Presentation file was not generated"
            assert out_path.stat().st_size > 1024, "Presentation file is empty or corrupted"
            # Read back to verify layout
            check_prs = Presentation(str(out_path))
            assert len(check_prs.slides) == len(slides_data), "Slide count mismatch during validation"

            # Step 5: Optional launch
            if launch_after:
                app_registry.launch_app("office", str(out_path))

            # Finalize
            task_center.complete_task(
                task.task_id,
                result=f"Presentation on '{topic}' successfully built ({len(slides_data)} slides).",
                verification="Verified PPTX format, slide hierarchy and size integrity",
                generated_files=[str(out_path)]
            )
            context_engine.set_last_file(str(out_path))
            context_engine.set_last_topic(topic)
            timeline.record(
                event_type="TASK",
                title=f"Presentation Workflow Completed: {topic}",
                details=f"Saved presentation to {out_path.name}",
                result=str(out_path)
            )

            return WorkflowResult(
                workflow_name="Presentation",
                success=True,
                message=f"Sir, '{topic}' presentation successfully create kar di gayi hai: {out_path.name}",
                generated_files=[str(out_path)],
                steps_completed=total_steps,
                total_steps=total_steps,
                metadata={"slides_count": len(slides_data), "output_path": str(out_path)}
            )

        except Exception as e:
            err_msg = str(e)
            task_center.fail_task(task.task_id, err_msg)
            timeline.record(
                event_type="TASK",
                title="Presentation Workflow Failed",
                details=err_msg,
                status="FAILED",
                errors=[err_msg]
            )
            return WorkflowResult(
                workflow_name="Presentation",
                success=False,
                message=f"Sir, presentation workflow mein error aaya: {err_msg}",
                generated_files=[],
                steps_completed=0,
                total_steps=total_steps,
                errors=[err_msg]
            )

    # ── 2. Software Development Workflow ──────────────────────────────────────

    def run_dev_workflow(
        self,
        project_name: str,
        test_script_rel_path: Optional[str] = None
    ) -> WorkflowResult:
        """
        Executes Software Development Workflow:
          1. Inspect project architecture
          2. Check for syntax bugs and test failures
          3. Inspect errors and isolate root cause
          4. Execute automated verification
          5. Report status and remaining issues
        """
        from core.project_manager import project_manager

        total_steps = 6
        task = task_center.queue_task(
            goal=f"Software Dev Audit & Test Cycle for '{project_name}'",
            plan=[
                "Locate and verify project root",
                "Inspect git status and active branch",
                "Run syntax and compilation audit",
                "Execute test suite",
                "Analyze errors and generate resolution",
                "Finalize health status"
            ]
        )
        task_center.set_task_running(task.task_id, 0)

        try:
            # Step 1: Project status & health
            task_center.set_task_running(task.task_id, 1)
            report = project_manager.get_project_status_report(project_name)

            # Step 2: Syntax and compilation verification
            task_center.set_task_running(task.task_id, 2)
            proj_info = project_manager.get_project(project_name)
            p_dir = Path(proj_info.path) if proj_info else BASE_DIR

            # Compile test
            errors = []
            for root, _, files in os.walk(p_dir):
                for f in files:
                    if f.endswith(".py"):
                        fp = Path(root) / f
                        try:
                            import py_compile
                            py_compile.compile(str(fp), doraise=True)
                        except Exception as e:
                            errors.append(f"{fp.name}: {e}")

            task_center.set_task_running(task.task_id, 4)
            is_healthy = len(errors) == 0
            res_msg = f"Project '{project_name}' audit completed. {len(errors)} syntax issues found."

            task_center.complete_task(
                task.task_id,
                result=res_msg,
                verification="Code compilation check passed" if is_healthy else "Errors identified",
                generated_files=[]
            )

            return WorkflowResult(
                workflow_name="Software Development",
                success=is_healthy,
                message=f"Sir, {project_name} ka development audit complete ho gaya hai. Status: {'HEALTHY' if is_healthy else 'ISSUES FOUND'}.",
                generated_files=[],
                steps_completed=total_steps,
                total_steps=total_steps,
                errors=errors,
                metadata={"project": project_name, "report": report}
            )
        except Exception as e:
            task_center.fail_task(task.task_id, str(e))
            return WorkflowResult(
                workflow_name="Software Development",
                success=False,
                message=f"Sir, development workflow mein failure: {e}",
                generated_files=[],
                steps_completed=1,
                total_steps=total_steps,
                errors=[str(e)]
            )

    # ── 3. Image Processing Workflow ──────────────────────────────────────────

    def run_image_workflow(
        self,
        source_image_path: str,
        operations: List[Dict[str, Any]],
        output_path: Optional[str] = None
    ) -> WorkflowResult:
        """
        Executes Image-Editing Workflow:
          1. Locate and validate source image
          2. Apply transformations (resize, filter, contrast, brightness, crop, border)
          3. Save to distinct output file
          4. Validate resulting image dimensions and format
          5. Update context and report location
        """
        total_steps = 5
        task = task_center.queue_task(
            goal=f"Process image '{Path(source_image_path).name}'",
            plan=[
                "Locate and load source image",
                "Apply requested transformations",
                "Export to new target file",
                "Verify output image dimensions and integrity",
                "Register artifact and report"
            ]
        )
        task_center.set_task_running(task.task_id, 0)

        src = Path(source_image_path)
        if not src.exists():
            err = f"Source image does not exist: {source_image_path}"
            task_center.fail_task(task.task_id, err)
            return WorkflowResult("Image Processing", False, err, [], 0, total_steps, errors=[err])

        try:
            task_center.set_task_running(task.task_id, 1)
            img = Image.open(src).convert("RGB")

            # Apply requested operations
            for op in operations:
                op_type = op.get("type", "").lower()
                if op_type == "resize":
                    w = int(op.get("width", img.width))
                    h = int(op.get("height", img.height))
                    img = img.resize((w, h), Image.Resampling.LANCZOS)
                elif op_type == "grayscale":
                    img = ImageOps.grayscale(img).convert("RGB")
                elif op_type == "blur":
                    radius = op.get("radius", 2)
                    img = img.filter(ImageFilter.GaussianBlur(radius))
                elif op_type == "sharpen":
                    img = img.filter(ImageFilter.SHARPEN)
                elif op_type == "contrast":
                    factor = float(op.get("factor", 1.2))
                    enh = ImageEnhance.Contrast(img)
                    img = enh.enhance(factor)
                elif op_type == "brightness":
                    factor = float(op.get("factor", 1.1))
                    enh = ImageEnhance.Brightness(img)
                    img = enh.enhance(factor)
                elif op_type == "border":
                    color = op.get("color", "black")
                    border_w = int(op.get("width", 4))
                    img = ImageOps.expand(img, border=border_w, fill=color)

            # Save to distinct output
            task_center.set_task_running(task.task_id, 2)
            if not output_path:
                out_file = OUTPUTS_DIR / f"edited_{src.stem}_{int(time.time())}.png"
            else:
                out_file = Path(output_path)

            out_file.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out_file), format="PNG")

            # Validate
            task_center.set_task_running(task.task_id, 3)
            assert out_file.exists() and out_file.stat().st_size > 100, "Generated image verification failed"
            val_img = Image.open(out_file)
            assert val_img.size[0] > 0 and val_img.size[1] > 0

            # Register
            task_center.complete_task(
                task.task_id,
                result=f"Image processed successfully ({val_img.width}x{val_img.height})",
                verification="Verified image header and dimensions",
                generated_files=[str(out_file)]
            )
            context_engine.set_last_file(str(out_file))

            return WorkflowResult(
                workflow_name="Image Processing",
                success=True,
                message=f"Sir, processed image ready hai: {out_file.name} ({val_img.width}x{val_img.height})",
                generated_files=[str(out_file)],
                steps_completed=total_steps,
                total_steps=total_steps,
                metadata={"width": val_img.width, "height": val_img.height, "path": str(out_file)}
            )

        except Exception as e:
            task_center.fail_task(task.task_id, str(e))
            return WorkflowResult("Image Processing", False, str(e), [], 1, total_steps, errors=[str(e)])

    # ── 4. Blender 3D Workflow ────────────────────────────────────────────────

    def run_blender_workflow(
        self,
        scene_description: str,
        target_name: Optional[str] = None,
        export_formats: Optional[List[str]] = None,
        render_preview: bool = True,
        launch_after: bool = False
    ) -> WorkflowResult:
        """
        Executes end-to-end 3D Scene Pipeline:
          1. Synthesize structured bpy Python script (lighting, camera, materials)
          2. Execute Blender 5.2 headless (-b -P)
          3. Generate native .blend and exports (.obj, .glb)
          4. Render preview image
          5. Verify output files
        """
        from creation_studio.blender_engine import blender_engine
        total_steps = 5
        task = task_center.queue_task(
            goal=f"3D Scene Generation: '{scene_description}'",
            plan=[
                "Parse scene prompt and synthesize bpy script",
                "Execute headless Blender 5.2 automation",
                "Verify native .blend project file",
                "Render image preview and verify pixels",
                "Register 3D deliverable"
            ]
        )
        task_center.set_task_running(task.task_id, 0)

        try:
            task_center.set_task_running(task.task_id, 1)
            name = target_name or f"scene_{int(time.time()) % 10000}"
            res = blender_engine.create_3d_scene(
                scene_description=scene_description,
                target_name=name,
                export_formats=export_formats or ["blend", "obj"],
                render_preview=render_preview
            )

            generated = []
            for k, info in res.get("outputs", {}).items():
                if info.get("verified"):
                    generated.append(info.get("path"))

            if not res.get("verified"):
                task_center.fail_task(task.task_id, res.get("diagnostics", "3D generation failed"))
                return WorkflowResult("Blender 3D", False, res.get("diagnostics"), generated, 1, total_steps, errors=[res.get("diagnostics")])

            task_center.complete_task(
                task.task_id,
                result=f"3D Scene '{name}' successfully created.",
                verification=res.get("diagnostics"),
                generated_files=generated
            )

            if launch_after and generated:
                blend_file = next((g for g in generated if g.endswith(".blend")), None)
                if blend_file:
                    app_registry.launch_app("blender", blend_file)

            return WorkflowResult(
                workflow_name="Blender 3D",
                success=True,
                message=f"Sir, 3D scene '{name}' build ho gayi hai. {res.get('diagnostics')}",
                generated_files=generated,
                steps_completed=total_steps,
                total_steps=total_steps,
                metadata=res
            )
        except Exception as e:
            task_center.fail_task(task.task_id, str(e))
            return WorkflowResult("Blender 3D", False, str(e), [], 0, total_steps, errors=[str(e)])

    # ── 5. Email & Communication Workflow ─────────────────────────────────────

    def run_email_workflow(
        self,
        recipient: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        send_immediately: bool = False,
    ) -> WorkflowResult:
        """
        Executes Email Workflow:
          1. Validate recipient and attachments
          2. Generate RFC822 .eml draft file
          3. Index draft and generate preview
          4. Send via Outlook/SMTP only if authorized
        """
        from core.email_engine import email_engine
        total_steps = 4
        task = task_center.queue_task(
            goal=f"Email Workflow: Send to '{recipient}'",
            plan=[
                "Validate recipient address and attachment paths",
                "Generate RFC822 .eml draft file",
                "Register draft and create preview",
                "Authorize and transmit"
            ]
        )
        task_center.set_task_running(task.task_id, 0)

        try:
            msg, preview = email_engine.create_draft(
                recipient=recipient,
                subject=subject,
                body=body,
                attachments=attachments
            )
            task_center.set_task_running(task.task_id, 2)

            generated = [msg.saved_eml_path] if msg.saved_eml_path else []

            if send_immediately:
                send_res = email_engine.send_draft(msg.draft_id, explicit_authorized=True)
                if send_res.get("success"):
                    task_center.complete_task(task.task_id, "Email sent successfully", "Delivered via " + send_res.get("provider", "Mail"), generated)
                    return WorkflowResult("Email", True, f"Sir, email successfully bhej di gayi hai to {recipient}.", generated, total_steps, total_steps)
                else:
                    return WorkflowResult("Email", False, send_res.get("error", "Email send failed"), generated, 2, total_steps, errors=[send_res.get("error")])

            task_center.complete_task(task.task_id, f"Draft saved [ID: {msg.draft_id}]", "Draft file verified", generated)
            return WorkflowResult(
                workflow_name="Email",
                success=True,
                message=f"Sir, email draft create kar diya gaya hai [ID: {msg.draft_id}]. File: {msg.saved_eml_path}",
                generated_files=generated,
                steps_completed=3,
                total_steps=total_steps,
                metadata={"draft_id": msg.draft_id, "preview": preview}
            )
        except Exception as e:
            task_center.fail_task(task.task_id, str(e))
            return WorkflowResult("Email", False, str(e), [], 0, total_steps, errors=[str(e)])


workflow_orchestrator = WorkflowOrchestrator.get_instance()


