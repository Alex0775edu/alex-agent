"""
actions/creation_engine.py — Universal Multimodal Creation Engine for ALEX 3.0 Workstation.

Workflow:
  Understand Request -> Generate Structure -> Build Native Asset -> Verify -> Report

Generates & Creates:
  • Presentations (.pptx): Multi-slide, professional structure, title + content + conclusions.
  • Word Documents (.docx): Formatted sections, headings, bullet points, executive reports.
  • Excel Spreadsheets (.xlsx): Multi-sheet workbooks, headers, formulas, styled data tables.
  • Markdown & Text reports (.md, .txt)
  • Python & Web code scripts (.py, .html, .js, .json)
  • 3D Assets (.obj, .gltf, .stl): Parametric geometry generators (cubes, cylinders, spheres,
    robot primitives, mechanical meshes) with native export when Blender is headless/optional.
  • Image Processing & Edits (.png, .jpg, .webp): Crop, resize, enhance, sharpen, contrast, watermarking.

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.security import security_manager, OWNER_ADDRESS

# Ensure Desktop/Documents default path
def _get_target_dir(target_folder: str = "") -> Path:
    if target_folder:
        folder = Path(target_folder).expanduser().resolve()
    else:
        desktop = Path.home() / "Desktop"
        folder = desktop if desktop.exists() else Path.home() / "Documents"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_presentation(
    title: str,
    slides: List[Dict[str, Any]] | str,
    filename: str = "",
    target_folder: str = "",
    slide_count: int = 0,
    export_pdf: bool = False,
    open_in_powerpoint: bool = False,
) -> str:
    """
    Creates a real, professional PowerPoint presentation (.pptx) with configurable slide count,
    consistent themes, tables, speaker notes, and optional PDF export via PowerPoint COM.
    """
    folder = _get_target_dir(target_folder)
    clean_name = filename.strip() or f"{title.lower().replace(' ', '_')[:30]}.pptx"
    if not clean_name.endswith(".pptx"):
        clean_name += ".pptx"
    target_path = folder / clean_name

    timeline.record("CREATION", f"Creating Presentation: {clean_name}", f"Title: {title}")

    try:
        from creation_studio.presentation_builder import PresentationBuilder
        pb = PresentationBuilder(folder)

        # Detect slide count if requested in title/prompt (e.g. "12 slides", "15 slides")
        detected_count = slide_count
        if detected_count <= 0:
            m = re.search(r"(\d+)\s*(?:slides?|slide|pages?)", f"{title} {clean_name}", re.IGNORECASE)
            if m:
                detected_count = int(m.group(1))

        out_path, val, pdf_path = pb.build_presentation(
            title=title,
            slides_data=slides,
            filename=clean_name,
            slide_count=detected_count,
            export_pdf=export_pdf
        )

        timeline.record("CREATION", f"Presentation Created: {clean_name}", f"{val.element_count} slides, {val.file_size_bytes} bytes", status="SUCCESS")

        pdf_msg = f"\n• PDF Export: {pdf_path} (Exported via PowerPoint COM)" if pdf_path else ""

        # Open in PowerPoint if requested
        if open_in_powerpoint:
            from core.app_adapters import app_registry
            app_registry.launch_app("powerpoint", str(out_path))

        return (
            f"{OWNER_ADDRESS}, presentation '{clean_name}' successfully create kar di gayi hai!\n"
            f"• Location: {out_path}\n"
            f"• Total Slides: {val.element_count}\n"
            f"• File Size: {val.file_size_bytes} bytes"
            f"{pdf_msg}\n"
            f"Aap ise Microsoft PowerPoint ya kisi bhi PPT viewer me directly open kar sakte hain."
        )

    except Exception as e:
        timeline.record("CREATION", f"Presentation Failed: {clean_name}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, presentation create karne me error aaya: {e}"



def create_word_document(
    title: str,
    sections: List[Dict[str, Any]] | str,
    filename: str = "",
    target_folder: str = ""
) -> str:
    """
    Creates a formatted Microsoft Word document (.docx) with python-docx and verifies it.
    """
    folder = _get_target_dir(target_folder)
    clean_name = filename.strip() or f"{title.lower().replace(' ', '_')[:30]}.docx"
    if not clean_name.endswith(".docx"):
        clean_name += ".docx"
    target_path = folder / clean_name

    timeline.record("CREATION", f"Creating Word Document: {clean_name}", f"Title: {title}")

    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor

        doc = Document()
        # Title
        doc.add_heading(title, level=0)
        p_sub = doc.add_paragraph()
        r = p_sub.add_run("Prepared by ALEX Workstation for Aditya Sir")
        r.italic = True

        # Process sections
        sec_list: List[Dict[str, Any]] = []
        if isinstance(sections, str):
            try:
                parsed = json.loads(sections)
                if isinstance(parsed, list):
                    sec_list = parsed
            except Exception:
                # Markdown-style parsing
                current_sec = {"heading": "Overview", "content": []}
                for line in sections.split("\n"):
                    line_s = line.strip()
                    if line_s.startswith("#"):
                        if current_sec["content"]:
                            sec_list.append(current_sec)
                        current_sec = {"heading": line_s.lstrip("# ").strip(), "content": []}
                    elif line_s:
                        current_sec["content"].append(line_s)
                if current_sec["content"]:
                    sec_list.append(current_sec)
        elif isinstance(sections, list):
            sec_list = sections

        for sec in sec_list:
            h = sec.get("heading", "")
            if h:
                doc.add_heading(h, level=1)
            content_items = sec.get("content", [])
            if isinstance(content_items, str):
                content_items = [content_items]
            for item in content_items:
                if str(item).startswith(("-", "*", "•")):
                    doc.add_paragraph(str(item).lstrip("-*• ").strip(), style="List Bullet")
                else:
                    doc.add_paragraph(str(item))

        doc.save(str(target_path))
        size = target_path.stat().st_size
        timeline.record("CREATION", f"Word Doc Created: {clean_name}", f"{size} bytes", status="SUCCESS")

        return (
            f"{OWNER_ADDRESS}, Word document '{clean_name}' successfully build aur verify ho gaya hai.\n"
            f"• Location: {target_path}\n"
            f"• Size: {size} bytes\n"
            f"Ready in Microsoft Word format."
        )
    except Exception as e:
        timeline.record("CREATION", f"Word Doc Failed: {clean_name}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, Word document creation me error aaya: {e}"


def create_spreadsheet(
    title: str,
    sheets: Dict[str, List[List[Any]]] | List[List[Any]],
    filename: str = "",
    target_folder: str = "",
    include_chart: bool = True,
    chart_type: str = "bar",
    open_in_excel: bool = False,
) -> str:
    """
    Creates a styled Microsoft Excel workbook (.xlsx) with openpyxl, native charts,
    formula summaries (=SUM), and verifies it.
    """
    folder = _get_target_dir(target_folder)
    clean_name = filename.strip() or f"{title.lower().replace(' ', '_')[:30]}.xlsx"
    if not clean_name.endswith(".xlsx"):
        clean_name += ".xlsx"
    target_path = folder / clean_name

    timeline.record("CREATION", f"Creating Spreadsheet: {clean_name}", f"Title: {title}")

    try:
        from creation_studio.spreadsheet_studio import SpreadsheetStudio
        studio = SpreadsheetStudio(folder)

        # Check if single sheet with numeric data to add chart
        if include_chart and isinstance(sheets, list) and len(sheets) > 1:
            out_path, val = studio.create_chart_workbook(
                title=title,
                data_rows=sheets,
                chart_type=chart_type,
                filename=clean_name
            )
        else:
            out_path, val = studio.create_workbook(
                title=title,
                sheets_data=sheets,
                filename=clean_name,
                add_summary_row=True
            )

        timeline.record("CREATION", f"Spreadsheet Created: {clean_name}", f"{val.file_size_bytes} bytes", status="SUCCESS")

        if open_in_excel:
            from core.app_adapters import app_registry
            app_registry.launch_app("excel", str(out_path))

        return (
            f"{OWNER_ADDRESS}, Excel spreadsheet '{clean_name}' successfully create ho gaya hai.\n"
            f"• Location: {out_path}\n"
            f"• Size: {val.file_size_bytes} bytes\n"
            f"• Details: {val.integrity_notes}\n"
            f"Aap ise Microsoft Excel me open karke inspect kar sakte hain."
        )
    except Exception as e:
        timeline.record("CREATION", f"Spreadsheet Failed: {clean_name}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, spreadsheet create karne me error: {e}"



def create_3d_asset(
    asset_type: str = "robot",
    filename: str = "",
    target_folder: str = "",
    format: str = "blend",
    render_preview: bool = True,
    open_in_blender: bool = False,
) -> str:
    """
    Generates real 3D assets and scene files for Blender workflows:
    1. Connects to BlenderEngine to generate structured bpy scene code (lighting, cameras, materials).
    2. Executes headless Blender (blender -b -P script.py) to save native .blend and exported .obj/.glb.
    3. Renders high-quality preview image when feasible.
    4. Provides procedural mesh fallback if Blender binary is not found.
    """
    folder = _get_target_dir(target_folder)
    clean_name = filename.strip() or f"{asset_type.lower().replace(' ', '_')}"
    timeline.record("CREATION", f"Generating 3D Asset: {clean_name}", f"Type: {asset_type}, Format: {format}")

    try:
        from creation_studio.blender_engine import blender_engine
        # Ensure outputs go to requested folder or default 3D artifacts dir
        formats_list = ["blend", "obj"]
        if format.lower() in ("glb", "gltf"):
            formats_list.append("glb")
        elif format.lower() == "stl":
            formats_list.append("stl")

        scene_res = blender_engine.create_3d_scene(
            scene_description=asset_type,
            target_name=clean_name,
            export_formats=formats_list,
            render_preview=render_preview
        )

        outputs = scene_res.get("outputs", {})
        blend_info = outputs.get("blend", {})
        preview_info = outputs.get("preview", {})
        obj_info = outputs.get("obj", {})

        main_path = blend_info.get("path") or obj_info.get("path")
        timeline.record("CREATION", f"3D Asset Ready: {clean_name}", f"Status: {scene_res['status']}", status="SUCCESS")

        preview_msg = f"\n• Rendered Preview: {preview_info.get('path')}" if preview_info.get("verified") else ""
        blend_msg = f"\n• Native .blend Project: {blend_info.get('path')}" if blend_info.get("verified") else ""
        obj_msg = f"\n• Universal 3D OBJ: {obj_info.get('path')}" if obj_info.get("verified") else ""

        if open_in_blender and blend_info.get("path"):
            from core.app_adapters import app_registry
            app_registry.launch_app("blender", blend_info.get("path"))

        return (
            f"{OWNER_ADDRESS}, 3D scene '{clean_name}' successfully build ho gayi hai!\n"
            f"• Status: {scene_res['status']}\n"
            f"• Execution: {'Native Blender 5.2 (Headless Engine)' if scene_res.get('blender_executed') else 'Procedural 3D Mesh Generator'}"
            f"{blend_msg}"
            f"{obj_msg}"
            f"{preview_msg}\n"
            f"• Diagnostics: {scene_res.get('diagnostics', 'Verified on disk')}"
        )
    except Exception as e:
        timeline.record("CREATION", f"3D Model Failed: {clean_name}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, 3D model create karne me error aaya: {e}"



def process_image_asset(
    image_path: str,
    operation: str = "enhance",
    params: Dict[str, Any] | None = None
) -> str:
    """
    Real, functional image processing using Pillow and OpenCV.
    Operations:
      - 'crop': Crop to rect (box: [left, top, right, bottom])
      - 'resize': Resize dimensions (width, height)
      - 'rotate': Rotate angle (degrees)
      - 'enhance': Adjust contrast, brightness, sharpness
      - 'convert': Convert to png, jpg, webp, tiff
      - 'watermark': Overlay owner watermark 'ALEX | Sir'
    """
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        return f"{OWNER_ADDRESS}, image file '{image_path}' not found."

    op = operation.lower().strip()
    param_dict = params or {}
    timeline.record("CREATION", f"Image Operation: {op}", f"File: {src.name}")

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
        img = Image.open(src)
        out_name = f"{src.stem}_{op}{src.suffix}"
        dst = src.parent / out_name

        if op == "resize":
            w = int(param_dict.get("width", img.width // 2))
            h = int(param_dict.get("height", img.height // 2))
            res = img.resize((w, h), Image.Resampling.LANCZOS)
            res.save(dst)
        elif op == "crop":
            box = param_dict.get("box", [0, 0, img.width // 2, img.height // 2])
            res = img.crop(tuple(box))
            res.save(dst)
        elif op == "rotate":
            deg = float(param_dict.get("degrees", 90))
            res = img.rotate(deg, expand=True)
            res.save(dst)
        elif op == "enhance":
            contrast = float(param_dict.get("contrast", 1.25))
            sharpness = float(param_dict.get("sharpness", 1.3))
            brightness = float(param_dict.get("brightness", 1.05))
            e1 = ImageEnhance.Contrast(img).enhance(contrast)
            e2 = ImageEnhance.Sharpness(e1).enhance(sharpness)
            res = ImageEnhance.Brightness(e2).enhance(brightness)
            res.save(dst)
        elif op == "watermark":
            res = img.copy()
            draw = ImageDraw.Draw(res)
            text = "ALEX • Aditya Sir Workstation"
            draw.text((20, res.height - 40), text, fill=(255, 255, 255))
            res.save(dst)
        elif op == "convert":
            target_fmt = param_dict.get("format", "png").lower().lstrip(".")
            out_name = f"{src.stem}_converted.{target_fmt}"
            dst = src.parent / out_name
            if target_fmt in ("jpg", "jpeg") and img.mode in ("RGBA", "P"):
                res = img.convert("RGB")
            else:
                res = img
            res.save(dst)
        else:
            return f"Aditya Sir, unknown image operation: '{op}'. Supported: resize, crop, rotate, enhance, watermark, convert."

        size = dst.stat().st_size
        timeline.record("CREATION", f"Image Processed: {dst.name}", f"Size: {size} bytes", status="SUCCESS")

        return (
            f"Aditya Sir, image operation '{op}' successfully complete ho gayi hai.\n"
            f"• Result File: {dst}\n"
            f"• Output Dimensions: {res.width}x{res.height} px\n"
            f"• File Size: {size} bytes"
        )
    except Exception as e:
        timeline.record("CREATION", f"Image Op Failed: {src.name}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, image processing me error: {e}"


def create_document(
    filename: str,
    content: str,
    content_type: str = "markdown",
    target_folder: str = ""
) -> str:
    """
    Creates a new document, report, or script on disk for the owner and verifies it.
    Supports: markdown, docx, pptx, xlsx, python, json, text, 3d, image.
    """
    folder = _get_target_dir(target_folder)
    clean_type = content_type.lower().strip()

    # Route specialized media/document workflows
    if clean_type in ("pptx", "presentation"):
        return create_presentation(title=filename, slides=content, filename=filename, target_folder=str(folder))
    elif clean_type in ("docx", "word"):
        return create_word_document(title=filename, sections=content, filename=filename, target_folder=str(folder))
    elif clean_type in ("xlsx", "excel", "spreadsheet", "sheets"):
        # If content is string or list, route to create_spreadsheet
        try:
            parsed_data = json.loads(content) if isinstance(content, str) and content.strip().startswith(("[", "{")) else [["Item", "Value"], [filename, "Generated"]]
        except Exception:
            parsed_data = [["Item", "Value"], [filename, content]]
        return create_spreadsheet(title=filename, sheets=parsed_data, filename=filename, target_folder=str(folder))
    elif clean_type in ("3d", "obj", "model", "blend", "blender"):
        return create_3d_asset(asset_type=filename, filename=filename, target_folder=str(folder))


    timeline.record("CREATION", f"Creating File: {filename}", f"Type: {content_type}")
    target_path = folder / filename

    try:
        target_path.write_text(content, encoding="utf-8")
        size = target_path.stat().st_size

        timeline.record("CREATION", f"File Created: {filename}", f"Size: {size} bytes at {target_path}", status="SUCCESS")

        try:
            from core.proactive_intelligence import proactive_engine
            proactive_engine.notify_file_ready(filename, str(target_path))
        except Exception:
            pass

        return (
            f"{OWNER_ADDRESS}, file '{filename}' ({content_type}) successfully create kar di gayi hai.\n"
            f"Location: {target_path}\n"
            f"Size: {size} bytes."
        )
    except Exception as e:
        timeline.record("CREATION", f"Creation Failed: {filename}", str(e), status="FAILED")
        return f"{OWNER_ADDRESS}, file creation mein error aaya: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "create_document",
    "description": "Multimodal Creation Engine: Generates real PowerPoint presentations (.pptx), Word documents (.docx), Excel sheets (.xlsx), 3D assets (.obj), code, reports, and Markdown files on disk for Sir.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "filename": {
                "type": "STRING",
                "description": "Name of the file to create (e.g. 'LMS_Architecture.pptx', 'Audit_Report.docx', 'robot_model.obj', 'summary.md')"
            },
            "content": {
                "type": "STRING",
                "description": "Full content, outline, JSON structure, or markdown text"
            },
            "content_type": {
                "type": "STRING",
                "description": "Format/type: 'pptx', 'docx', 'xlsx', '3d', 'markdown', 'python', 'json', 'csv', 'text'"
            },
            "target_folder": {
                "type": "STRING",
                "description": "Optional directory path to save in (defaults to Desktop or Documents)"
            }
        },
        "required": ["filename", "content"]
    },
    "handler": create_document,
}
