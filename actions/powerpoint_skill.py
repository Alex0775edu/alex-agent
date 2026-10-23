"""
actions/powerpoint_skill.py — Professional PowerPoint Presentation Builder for ALEX.

Creates verified, multi-slide .pptx presentations from natural-language topics.
Supports theme selection, configurable slide count, speaker notes, PDF export,
and post-creation verification by reopening the generated file.

Owner: Aditya Rajak
Salutation: Aditya Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from core.security import OWNER_ADDRESS
except ImportError:
    OWNER_ADDRESS = "Sir"

try:
    from core.action_timeline import timeline
except ImportError:
    class _Stub:
        def record(self, *a, **kw): pass
    timeline = _Stub()

# ── Theme definitions ────────────────────────────────────────────────────────

def _rgb(r, g, b):
    """Lazily create RGBColor to avoid import at module level."""
    from pptx.dml.color import RGBColor
    return RGBColor(r, g, b)


THEMES = {
    "navy":    {"primary": (0x1E, 0x3A, 0x8A), "accent": (0x3B, 0x82, 0xF6), "text": (0xFF, 0xFF, 0xFF), "body": (0x1E, 0x29, 0x3B)},
    "emerald": {"primary": (0x06, 0x5F, 0x46), "accent": (0x10, 0xB9, 0x81), "text": (0xFF, 0xFF, 0xFF), "body": (0x1E, 0x29, 0x3B)},
    "crimson": {"primary": (0x9F, 0x12, 0x39), "accent": (0xFB, 0x72, 0x85), "text": (0xFF, 0xFF, 0xFF), "body": (0x1E, 0x29, 0x3B)},
    "dark":    {"primary": (0x1F, 0x29, 0x37), "accent": (0x94, 0xA3, 0xB8), "text": (0xF1, 0xF5, 0xF9), "body": (0xE2, 0xE8, 0xF0)},
}


# ── Outline generator ────────────────────────────────────────────────────────

def _generate_outline(topic: str, slide_count: int) -> List[Dict[str, Any]]:
    """Generates a structured slide outline for any given topic."""
    t = topic.strip()
    # Template structures that scale to requested slide count
    templates = [
        {"title": f"Introduction to {t}", "points": [
            f"What is {t} and why it matters",
            "Historical context and evolution",
            "Current landscape and relevance",
        ], "notes": f"Begin with a high-level overview of {t}. Establish context."},

        {"title": "Key Concepts & Fundamentals", "points": [
            f"Core principles underlying {t}",
            "Essential terminology and definitions",
            "Foundational theories and frameworks",
        ], "notes": "Define key terms so the audience is on the same page."},

        {"title": "Architecture & Framework", "points": [
            f"Structural components of {t}",
            "How the parts interact and integrate",
            "Scalability and design considerations",
        ], "notes": "Walk through the logical or physical architecture."},

        {"title": "Core Features & Capabilities", "points": [
            f"Primary capabilities of {t}",
            "Unique differentiators and innovations",
            "Performance characteristics and benchmarks",
        ], "notes": "Highlight what makes this solution stand out."},

        {"title": "Implementation Strategy", "points": [
            "Step-by-step adoption roadmap",
            "Prerequisites and dependency management",
            "Risk mitigation and contingency planning",
        ], "notes": "Provide a practical implementation pathway."},

        {"title": "Benefits & Advantages", "points": [
            f"Measurable value delivered by {t}",
            "Efficiency gains and cost reduction",
            "Competitive advantages and market impact",
        ], "notes": "Quantify benefits where possible with metrics."},

        {"title": "Challenges & Considerations", "points": [
            "Known limitations and constraints",
            "Common pitfalls and how to avoid them",
            "Resource requirements and trade-offs",
        ], "notes": "Be transparent about challenges to build credibility."},

        {"title": "Real-World Applications", "points": [
            f"Practical use cases for {t}",
            "Industry adoption and case studies",
            "Success stories and lessons learned",
        ], "notes": "Ground the presentation with real examples."},

        {"title": "Data & Performance Metrics", "points": [
            "Key performance indicators and measurements",
            "Benchmark results and comparative analysis",
            "Scalability and stress testing insights",
        ], "notes": "Support claims with empirical data."},

        {"title": "Technology Stack & Tools", "points": [
            f"Technologies powering {t}",
            "Integration with existing ecosystems",
            "Tool recommendations and best practices",
        ], "notes": "Detail the technical stack."},

        {"title": "Security & Compliance", "points": [
            "Security architecture and safeguards",
            "Regulatory compliance requirements",
            "Data privacy and protection measures",
        ], "notes": "Address security concerns proactively."},

        {"title": "Future Roadmap", "points": [
            "Upcoming features and enhancements",
            f"Long-term vision for {t}",
            "Research directions and innovation pipeline",
        ], "notes": "Show forward-thinking vision."},

        {"title": "Summary & Key Takeaways", "points": [
            f"Core value proposition of {t}",
            "Critical success factors",
            "Immediate next steps and action items",
        ], "notes": "Reinforce the most important points."},

        {"title": "Questions & Discussion", "points": [
            "Open floor for questions",
            f"Contact information for {t} discussions",
            f"Prepared by ALEX for {OWNER_ADDRESS}",
        ], "notes": "Invite discussion and wrap up."},
    ]

    # Select the right number of slides
    count = max(3, min(slide_count, len(templates)))
    if count <= 5:
        indices = [0, 1, 3, 5, -2][:count]
    elif count <= 8:
        step = len(templates) / count
        indices = [int(i * step) for i in range(count)]
    else:
        indices = list(range(min(count, len(templates))))

    return [templates[i] for i in indices[:count]]


# ── Default output directory ─────────────────────────────────────────────────

def _get_target_dir(target_folder: str = "") -> Path:
    if target_folder:
        folder = Path(target_folder).expanduser().resolve()
    else:
        desktop = Path.home() / "Desktop"
        folder = desktop if desktop.exists() else Path.home() / "Documents"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ── PDF export via COM ───────────────────────────────────────────────────────

def _export_pdf_via_com(pptx_path: Path) -> Optional[Path]:
    """Attempts to export a PPTX to PDF using PowerPoint COM automation."""
    try:
        import win32com.client
        ppt_app = win32com.client.Dispatch("PowerPoint.Application")
        ppt_app.Visible = False
        presentation = ppt_app.Presentations.Open(
            str(pptx_path.resolve()), WithWindow=False
        )
        pdf_path = pptx_path.with_suffix(".pdf")
        # 32 = ppFixedFormatTypePDF
        presentation.SaveAs(str(pdf_path.resolve()), 32)
        presentation.Close()
        ppt_app.Quit()
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path
    except Exception as e:
        print(f"[PowerPoint] COM PDF export failed: {e}")
    return None


# ── Main handler ─────────────────────────────────────────────────────────────

def create_presentation(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Creates a verified, professional PowerPoint presentation."""
    params = parameters or {}
    topic = params.get("topic", "").strip()
    if not topic:
        return f"{OWNER_ADDRESS}, presentation ke liye topic specify karein."

    slide_count = int(params.get("slide_count", 10))
    theme_name = params.get("theme", "navy").lower().strip()
    filename = params.get("filename", "").strip()
    target_folder = params.get("target_folder", "").strip()
    open_after = str(params.get("open_after", "false")).lower() in ("true", "1", "yes", "haan")
    export_pdf = str(params.get("export_pdf", "false")).lower() in ("true", "1", "yes", "haan")

    # Resolve output path
    folder = _get_target_dir(target_folder)
    clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', topic.lower())[:35]}.pptx"
    if not clean_name.endswith(".pptx"):
        clean_name += ".pptx"
    target_path = folder / clean_name

    timeline.record("CREATION", f"Creating Presentation: {clean_name}", f"Topic: {topic}, Slides: {slide_count}")

    # Generate slides outline
    slides_data = _generate_outline(topic, slide_count)

    # Check for structured slides passed via JSON
    slides_input = params.get("slides_json", "")
    if slides_input:
        try:
            parsed = json.loads(slides_input) if isinstance(slides_input, str) else slides_input
            if isinstance(parsed, list) and parsed:
                slides_data = parsed
        except Exception:
            pass

    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        theme = THEMES.get(theme_name, THEMES["navy"])
        primary = RGBColor(*theme["primary"])
        accent = RGBColor(*theme["accent"])
        text_color = RGBColor(*theme["text"])
        body_color = RGBColor(*theme["body"])

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # ── Slide 1: Title Slide ─────────────────────────────────────────
        title_layout = prs.slide_layouts[0]
        s1 = prs.slides.add_slide(title_layout)
        s1.shapes.title.text = topic
        for run in s1.shapes.title.text_frame.paragraphs[0].runs:
            run.font.size = Pt(36)
            run.font.bold = True
            run.font.color.rgb = primary

        if len(s1.placeholders) > 1:
            sub = s1.placeholders[1]
            sub.text = f"Prepared by ALEX for {OWNER_ADDRESS}"
            for run in sub.text_frame.paragraphs[0].runs:
                run.font.size = Pt(16)
                run.font.italic = True
                run.font.color.rgb = accent

        notes1 = s1.notes_slide.notes_text_frame
        notes1.text = f"Welcome. Today's presentation covers: {topic}. {len(slides_data)} content slides follow."

        # ── Content Slides ───────────────────────────────────────────────
        content_layout = prs.slide_layouts[1]
        for slide_info in slides_data:
            s_title = slide_info.get("title", "Slide")
            s_points = slide_info.get("points", [])
            s_notes = slide_info.get("notes", "")

            slide = prs.slides.add_slide(content_layout)

            # Style title
            slide.shapes.title.text = s_title
            for run in slide.shapes.title.text_frame.paragraphs[0].runs:
                run.font.size = Pt(28)
                run.font.bold = True
                run.font.color.rgb = primary

            # Content body
            tf = slide.placeholders[1].text_frame
            tf.clear()
            for idx, pt in enumerate(s_points):
                if idx == 0:
                    tf.text = str(pt)
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                    p.text = str(pt)
                p.space_after = Pt(8)
                for run in p.runs:
                    run.font.size = Pt(18)
                    run.font.color.rgb = body_color

            # Speaker notes
            if s_notes:
                slide.notes_slide.notes_text_frame.text = str(s_notes)

        prs.save(str(target_path))

        # ── Verification: reopen and check ───────────────────────────────
        verify_msg = ""
        try:
            verify_prs = Presentation(str(target_path))
            actual_count = len(verify_prs.slides)
            verify_msg = f"✅ Verified: {actual_count} slides confirmed by reopening the file."
        except Exception as ve:
            verify_msg = f"⚠️ Verification warning: {ve}"

        size = target_path.stat().st_size
        total_slides = len(prs.slides)

        timeline.record("CREATION", f"Presentation Created: {clean_name}",
                        f"{total_slides} slides, {size} bytes, theme={theme_name}",
                        status="SUCCESS")

        # ── PDF export ───────────────────────────────────────────────────
        pdf_msg = ""
        if export_pdf:
            pdf_path = _export_pdf_via_com(target_path)
            if pdf_path:
                pdf_msg = f"\n• PDF Export: {pdf_path} ({pdf_path.stat().st_size} bytes)"
            else:
                pdf_msg = "\n• PDF Export: PowerPoint COM not available. Open the .pptx and export manually."

        # ── Open in PowerPoint ───────────────────────────────────────────
        open_msg = ""
        if open_after:
            try:
                os.startfile(str(target_path))
                open_msg = "\n• PowerPoint mein automatically open ho raha hai."
            except Exception as oe:
                open_msg = f"\n• PowerPoint open nahi ho saka: {oe}"

        return (
            f"{OWNER_ADDRESS}, professional presentation '{clean_name}' successfully create ho gayi hai!\n"
            f"• Topic: {topic}\n"
            f"• Total Slides: {total_slides} (1 title + {total_slides - 1} content)\n"
            f"• Theme: {theme_name}\n"
            f"• Location: {target_path}\n"
            f"• File Size: {size:,} bytes\n"
            f"• {verify_msg}"
            f"{pdf_msg}"
            f"{open_msg}"
        )

    except ImportError:
        timeline.record("CREATION", f"Presentation Failed: {clean_name}",
                        "python-pptx not installed", status="FAILED")
        return (
            f"{OWNER_ADDRESS}, python-pptx library install nahi hai. "
            f"Install karein: pip install python-pptx"
        )
    except Exception as e:
        timeline.record("CREATION", f"Presentation Failed: {clean_name}",
                        str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, presentation create karne mein error aaya: {e}"


# ── Tool declaration ─────────────────────────────────────────────────────────
TOOL = {
    "name": "create_presentation",
    "description": (
        "Creates a complete, professional PowerPoint presentation (.pptx) with multiple slides, "
        "structured content, speaker notes, and a consistent theme. Use for any PPT/presentation request. "
        "The presentation is saved to disk, verified by reopening, and optionally opened in PowerPoint."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {
                "type": "STRING",
                "description": "The presentation topic or title (e.g. 'Artificial Intelligence', 'Project Status Report')"
            },
            "slide_count": {
                "type": "STRING",
                "description": "Number of content slides to generate (default: 10, max: 14)"
            },
            "theme": {
                "type": "STRING",
                "description": "Color theme: navy (default), emerald, crimson, or dark"
            },
            "filename": {
                "type": "STRING",
                "description": "Output filename (e.g. 'AI_Presentation.pptx'). Auto-generated if empty."
            },
            "target_folder": {
                "type": "STRING",
                "description": "Folder to save in (defaults to Desktop)"
            },
            "open_after": {
                "type": "STRING",
                "description": "'true' to open the presentation in PowerPoint after creation"
            },
            "export_pdf": {
                "type": "STRING",
                "description": "'true' to also export as PDF (requires PowerPoint installed)"
            },
            "slides_json": {
                "type": "STRING",
                "description": "Optional JSON array of slide objects: [{title, points: [...], notes}, ...]"
            },
        },
        "required": ["topic"],
    },
    "handler": create_presentation,
}

