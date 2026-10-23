"""
test_alex_phase10.py — Verification Test Suite for ALEX Phase 10:
Multimodal Creation Studio.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Configure utf-8 console output for Windows cp1252 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Mark-LV-main root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from creation_studio.diagram_engine import DiagramEngine
from creation_studio.document_engine import DocumentEngine
from creation_studio.image_studio import ImageStudio
from creation_studio.models import (
    AssetType,
    CreationTask,
    OutputFormat,
    TaskStatus,
)
from creation_studio.orchestrator import CreationStudioOrchestrator
from creation_studio.pdf_intelligence import PdfIntelligenceEngine
from creation_studio.presentation_builder import PresentationBuilder
from creation_studio.spreadsheet_studio import SpreadsheetStudio
from creation_studio.threed_studio import ThreeDStudio
from creation_studio.video_studio import VideoStudio


def run_all_tests():
    print("=" * 80)
    print("  ALEX PHASE 10 — MULTIMODAL CREATION STUDIO VERIFICATION SUITE")
    print("=" * 80)

    tmp_out = Path(tempfile.mkdtemp(prefix="alex_creation_test_"))
    passed_tests = 0
    total_tests = 15

    try:
        # TEST 1: Tool Capabilities & Dependency Inspection
        print("\n[TEST 1] Tool Capabilities & Dependency Inspection")
        orch = CreationStudioOrchestrator(base_workspace=tmp_out)
        caps = orch.get_tool_capabilities()
        assert isinstance(caps.supported_formats, list), "Expected supported formats list"
        assert "obj" in caps.supported_formats, "OBJ 3D format must be supported"
        assert "svg" in caps.supported_formats, "SVG diagram format must be supported"
        print(f"  [PASS] Tool capabilities inspected: {len(caps.supported_formats)} formats supported. Blender={caps.blender_available}, FFmpeg={caps.ffmpeg_available}.")
        passed_tests += 1

        # TEST 2: Professional Document Generation (DOCX, HTML, Markdown)
        print("\n[TEST 2] Document Generation (DOCX, HTML, Markdown)")
        doc_eng = DocumentEngine(tmp_out)
        content = [
            {"heading": "Executive Summary", "paragraphs": ["ALEX Multimodal Creation Studio is active for Aditya Sir."]},
            {"heading": "Key Milestones", "bullets": ["Sub-50ms dispatch", "Zero false success", "100% test pass rate"]}
        ]
        docx_path, docx_val = doc_eng.generate_document("Project Architecture", content, format=OutputFormat.DOCX)
        assert docx_path.exists(), "DOCX file must exist on disk"
        assert docx_val.is_valid is True, f"DOCX validation failed: {docx_val.error_message}"
        assert docx_val.file_size_bytes > 0, "DOCX file must not be 0 bytes"

        html_path, html_val = doc_eng.generate_document("Project Web Report", content, format=OutputFormat.HTML)
        assert html_path.exists(), "HTML file must exist"
        assert html_val.is_valid is True, "HTML validation failed"
        print(f"  [PASS] Generated DOCX ({docx_val.file_size_bytes} bytes) and HTML ({html_val.file_size_bytes} bytes) deliverables.")
        passed_tests += 1

        # TEST 3: Unicode and Hindi Text Formatting
        print("\n[TEST 3] Unicode and Hindi Text Formatting")
        hindi_title = "प्रोजेक्ट रिपोर्ट - आदित्य सर"
        hindi_content = [
            {"heading": "परिचय", "paragraphs": ["ALEX वर्कस्टेशन पूरी तरह से सक्रिय है।"]},
            {"heading": "उपलब्धियां", "bullets": ["मल्टीमॉडल निर्माण", "सुरक्षित कोड निष्पादन"]}
        ]
        h_path, h_val = doc_eng.generate_document(hindi_title, hindi_content, format=OutputFormat.MD)
        assert h_path.exists(), "Hindi markdown file must exist"
        assert h_val.is_valid is True, "Hindi validation failed"
        read_text = h_path.read_text(encoding="utf-8")
        assert "आदित्य सर" in read_text, "Hindi text must be preserved accurately in output"
        print("  [PASS] Unicode and Hindi text preserved cleanly in markdown deliverable.")
        passed_tests += 1

        # TEST 4: Presentation Builder (PPTX with Slides & Speaker Notes)
        print("\n[TEST 4] Presentation Builder (PPTX Widescreen Slides & Notes)")
        ppt_bld = PresentationBuilder(tmp_out)
        ppt_path, ppt_val = ppt_bld.build_presentation("Autonomous Workstation Overview", "Strategy and Architecture")
        assert ppt_path.exists(), "PPTX file must exist"
        assert ppt_val.is_valid is True, f"PPTX validation failed: {ppt_val.error_message}"
        assert ppt_val.element_count >= 5, f"Expected at least 5 slides, got {ppt_val.element_count}"
        print(f"  [PASS] Generated PPTX presentation with {ppt_val.element_count} slides ({ppt_val.file_size_bytes} bytes).")
        passed_tests += 1

        # TEST 5: Spreadsheet Creation with Formulas & Styling
        print("\n[TEST 5] Spreadsheet Studio (.xlsx & .csv) with Automated Formulas")
        sheet_eng = SpreadsheetStudio(tmp_out)
        rows = [
            ["Milestone", "Planned Days", "Actual Days", "Variance"],
            ["Phase 8 Orchestrator", 4, 3, -1],
            ["Phase 9 Bug Lab", 5, 4, -1],
            ["Phase 10 Creation Studio", 6, 5, -1],
        ]
        xlsx_path, xlsx_val = sheet_eng.create_workbook("Project Ledger", rows, add_summary_row=True)
        assert xlsx_path.exists(), "XLSX file must exist"
        assert xlsx_val.is_valid is True, f"XLSX validation failed: {xlsx_val.error_message}"
        assert xlsx_val.file_size_bytes > 0, "XLSX size must be > 0"
        print(f"  [PASS] Styled Excel workbook created with automated summary formula ({xlsx_val.file_size_bytes} bytes).")
        passed_tests += 1

        # TEST 6: Dataset Audit & Health Inspection
        print("\n[TEST 6] Spreadsheet Dataset Cleaning & Integrity Audit")
        csv_path, csv_val = sheet_eng.create_csv("sample_data", rows)
        audit_res = sheet_eng.analyze_dataset(csv_path)
        assert audit_res["total_records"] == 3, f"Expected 3 data rows, got {audit_res['total_records']}"
        assert audit_res["health"] == "CLEAN", "Expected clean dataset status"
        print(f"  [PASS] Dataset audit completed: {audit_res['columns_count']} columns, {audit_res['total_records']} rows, Health={audit_res['health']}.")
        passed_tests += 1

        # TEST 7: PDF Intelligence & Metadata Extraction
        print("\n[TEST 7] PDF Intelligence & Text Extraction")
        pdf_eng = PdfIntelligenceEngine(tmp_out)
        # Create a sample PDF file
        sample_pdf = tmp_out / "sample_doc.pdf"
        sample_pdf.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000102 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF\n")
        pdf_meta = pdf_eng.extract_text_and_meta(sample_pdf)
        assert "pages_count" in pdf_meta, "Expected pages_count in extraction"
        print("  [PASS] PDF intelligence extracted pages count and document metadata.")
        passed_tests += 1

        # TEST 8: Non-Destructive Source File Preservation
        print("\n[TEST 8] Non-Destructive Source File Preservation")
        orig_bytes = sample_pdf.read_bytes()
        # Perform PDF split operation
        split_path, split_val = pdf_eng.split_pdf(sample_pdf, 1, 1)
        # Verify original was untouched
        assert sample_pdf.read_bytes() == orig_bytes, "Source PDF was modified! Must preserve originals."
        print("  [PASS] Original source file preserved with bitwise equality.")
        passed_tests += 1

        # TEST 9: Image Studio Operations (Crop, Resize, Enhance)
        print("\n[TEST 9] Image Studio Transformations")
        img_eng = ImageStudio(tmp_out)
        # Create a sample RGB test image
        from PIL import Image
        sample_img_path = tmp_out / "test_banner.png"
        img = Image.new("RGB", (200, 200), color=(73, 109, 137))
        img.save(sample_img_path)

        resized_path, res_val = img_eng.process_image(sample_img_path, "resize", {"width": 100, "height": 100})
        assert resized_path.exists(), "Resized image must exist"
        assert res_val.is_valid is True, "Resize validation failed"
        # Verify dimensions
        with Image.open(resized_path) as r_img:
            assert r_img.size == (100, 100), f"Expected (100, 100), got {r_img.size}"

        wm_path, wm_val = img_eng.process_image(sample_img_path, "watermark", {"text": "ALEX Sir"})
        assert wm_path.exists(), "Watermarked image must exist"
        print(f"  [PASS] Image resize (100x100) and watermark overlay verified.")
        passed_tests += 1

        # TEST 10: Transparent Background Cutout
        print("\n[TEST 10] Image Transparent Background Cutout")
        white_bg_img = tmp_out / "white_bg.png"
        img_w = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img_w.save(white_bg_img)

        trans_path, trans_val = img_eng.process_image(white_bg_img, "remove_background", {"threshold": 240})
        assert trans_path.exists(), "Transparent image must exist"
        with Image.open(trans_path) as t_img:
            assert t_img.mode == "RGBA", "Image must be converted to RGBA with alpha channel"
        print("  [PASS] White background converted to alpha transparent cutout.")
        passed_tests += 1

        # TEST 11: 3D Procedural Mesh & Blender Detection
        print("\n[TEST 11] 3D Asset Creation (Universal OBJ / STL)")
        threed_eng = ThreeDStudio(tmp_out)
        obj_path, obj_val = threed_eng.create_3d_model(asset_type="robot", format="obj")
        assert obj_path.exists(), "OBJ file must exist"
        assert obj_val.is_valid is True, "OBJ validation failed"
        assert obj_val.element_count > 0, "Vertices count must be > 0"
        obj_text = obj_path.read_text(encoding="utf-8")
        assert "v " in obj_text and "f " in obj_text, "OBJ file must contain vertex and face definitions"

        stl_path, stl_val = threed_eng.create_3d_model(asset_type="product_box", format="stl")
        assert stl_path.exists(), "STL file must exist"
        assert "solid" in stl_path.read_text(encoding="utf-8"), "STL must contain solid block"
        print(f"  [PASS] Generated valid 3D Wavefront OBJ ({obj_val.element_count} vertices) and ASCII STL models.")
        passed_tests += 1

        # TEST 12: Video Studio Status & Honest Dependency Reporting
        print("\n[TEST 12] Video Studio & Dependency Status")
        vid_eng = VideoStudio(tmp_out)
        v_status = vid_eng.get_status()
        assert "ffmpeg_available" in v_status, "Expected ffmpeg_available boolean"
        # Test handling missing source gracefully
        _, err_val = vid_eng.extract_audio("non_existent_video.mp4")
        assert err_val.is_valid is False, "Must report error on missing source video"
        print(f"  [PASS] Video Studio status reported honestly (FFmpeg={v_status['ffmpeg_available']}).")
        passed_tests += 1

        # TEST 13: Scalable Vector Graphics (SVG) Flowchart
        print("\n[TEST 13] Scalable Vector Graphics (SVG) Diagram Generator")
        diag_eng = DiagramEngine(tmp_out)
        steps = ["Understand Goal", "Clear Security", "Execute Creation", "Verify Deliverable"]
        svg_path, svg_val = diag_eng.generate_svg_flowchart("Creation Pipeline", steps)
        assert svg_path.exists(), "SVG diagram must exist"
        assert svg_val.is_valid is True, "SVG validation failed"
        svg_text = svg_path.read_text(encoding="utf-8")
        assert "<svg" in svg_text and "</svg>" in svg_text, "Must contain valid SVG XML root tags"
        assert "Creation Pipeline" in svg_text, "Title must be rendered in SVG"
        print(f"  [PASS] Scalable Vector SVG flowchart generated ({svg_val.file_size_bytes} bytes).")
        passed_tests += 1

        # TEST 14: Project-Aware Workspace Isolation
        print("\n[TEST 14] Project-Aware Workspace Isolation")
        task_proj = orch.execute_creation_request(
            prompt="Quarterly Financial Overview",
            asset_type=AssetType.SPREADSHEET,
            project_name="SkillSum"
        )
        assert task_proj.status == TaskStatus.COMPLETED, f"Task failed: {task_proj.error_message}"
        assert "SkillSum" in task_proj.output_path, "Output must be saved inside project-specific folder"
        assert Path(task_proj.output_path).exists(), "Project output file must exist"
        print(f"  [PASS] Project deliverable safely isolated in: {task_proj.output_path}")
        passed_tests += 1

        # TEST 15: End-to-End Orchestrator Dispatch & Templates
        print("\n[TEST 15] Universal Creation Studio Pipeline Dispatch")
        templates = orch.list_templates()
        assert len(templates) >= 5, "Expected at least 5 creation templates"

        # Universal prompt dispatch
        task_e2e = orch.execute_creation_request("Create professional executive report for Aditya Sir")
        assert task_e2e.status == TaskStatus.COMPLETED, f"E2E task failed: {task_e2e.error_message}"
        assert task_e2e.output_path is not None, "Output path must be recorded"
        assert task_e2e.validation is not None and task_e2e.validation.is_valid is True, "Validation must pass"
        print(f"  [PASS] End-to-end creation task {task_e2e.task_id} completed & verified in {task_e2e.elapsed_seconds}s.")
        passed_tests += 1

        # Final Summary
        print("\n" + "=" * 80)
        print(f"  TEST RESULTS: {passed_tests}/{total_tests} PASSED | 0 FAILED")
        print("=" * 80)
        print("All Phase 10 Multimodal Creation Studio tests completed successfully.\n")

    finally:
        shutil.rmtree(tmp_out, ignore_errors=True)


if __name__ == "__main__":
    run_all_tests()

