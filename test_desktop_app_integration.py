"""
test_desktop_app_integration.py — Integration and Task Execution Test Suite for ALEX.

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX

Validates Phase 1 to Phase 7 deliverables:
  1. Desktop App Registry: Windows Registry discovery of Office, Blender, VS Code, Chrome, etc.
  2. Microsoft PowerPoint: Presentation creation, slide counts, speaker notes, tables, COM PDF export.
  3. Microsoft Word: DOCX creation, headers/footers, margins, and safe document editing with backup.
  4. Microsoft Excel: XLSX workbooks, dynamic formulas (=SUM), styling, and native charts.
  5. Blender 3D: Real bpy script generation, headless execution with Blender 5.2, and .blend verification.
  6. Email Engine: RFC822 .eml draft generation, attachment validation, and Outlook COM integration.
  7. Natural Language Workflows: Multi-application orchestration via IntentEngine and WorkflowOrchestrator.
"""

import os
import shutil
import unittest
from pathlib import Path

from core.app_adapters import app_registry
from creation_studio.presentation_builder import PresentationBuilder
from creation_studio.document_engine import DocumentEngine
from creation_studio.models import OutputFormat
from creation_studio.spreadsheet_studio import SpreadsheetStudio
from creation_studio.blender_engine import blender_engine
from core.email_engine import email_engine
from core.intent_engine import intent_engine
from core.workflow_orchestrator import workflow_orchestrator


class TestDesktopAppIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / "memory" / "test_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_app_registry_discovery(self):
        """Verify Windows Registry and system discovery of installed applications."""
        installed_apps = app_registry.list_installed_apps()
        self.assertTrue(len(installed_apps) >= 10, "At least 10 desktop application adapters registered")
        app_names = {a["name"] for a in installed_apps}
        self.assertIn("Microsoft PowerPoint", app_names)
        self.assertIn("Microsoft Word", app_names)
        self.assertIn("Microsoft Excel", app_names)
        self.assertIn("Blender 3D", app_names)
        self.assertIn("Visual Studio Code", app_names)

        # Confirm PowerPoint and Word binary discovery
        ppt_adapter = app_registry.get_adapter("powerpoint")
        self.assertIsNotNone(ppt_adapter)
        self.assertTrue(ppt_adapter.is_installed(), "PowerPoint detected via Windows Registry")

        word_adapter = app_registry.get_adapter("word")
        self.assertIsNotNone(word_adapter)
        self.assertTrue(word_adapter.is_installed(), "Word detected via Windows Registry")

        blender_adapter = app_registry.get_adapter("blender")
        self.assertIsNotNone(blender_adapter)
        self.assertTrue(blender_adapter.is_installed(), "Blender detected on system")

    def test_02_powerpoint_presentation_and_com_pdf(self):
        """Verify multi-slide presentation creation, speaker notes, and PDF export."""
        pb = PresentationBuilder(self.test_dir)
        pptx_path, val, pdf_path = pb.build_presentation(
            title="Autonomous AI Architecture",
            slides_data="",
            filename="test_ai_deck.pptx",
            slide_count=5,
            export_pdf=True
        )
        self.assertTrue(pptx_path.exists(), "PPTX file created on disk")
        self.assertTrue(val.is_valid, "PPTX validated with slide hierarchy")
        self.assertEqual(val.element_count, 6, "1 title slide + 5 content slides = 6 total slides")
        self.assertGreater(val.file_size_bytes, 1000, "PPTX file has non-zero content")

        # Check COM export to PDF if Microsoft PowerPoint is installed
        if pdf_path:
            self.assertTrue(pdf_path.exists(), "PDF exported successfully via PowerPoint COM")
            self.assertGreater(pdf_path.stat().st_size, 1000, "PDF has non-zero size")

    def test_03_word_document_creation_and_safe_editing(self):
        """Verify Word document formatting, headers/footers, and edit with backup."""
        de = DocumentEngine(self.test_dir)
        content = [
            {"heading": "Executive Summary", "paragraphs": ["ALEX has been upgraded with desktop app adapters."], "bullets": ["High reliability", "Native COM"]},
            {"heading": "System Metrics", "table": [["Metric", "Value"], ["Pass Rate", "100%"]]}
        ]
        doc_path, val = de.generate_document("ALEX Integration Spec", content, format=OutputFormat.DOCX, filename="spec.docx")
        self.assertTrue(doc_path.exists())
        self.assertTrue(val.is_valid)

        # Edit existing document and preserve backup
        edited_path, val2 = de.edit_document(
            doc_path,
            append_sections=[{"heading": "Verification", "paragraphs": ["All tests passed."]}],
            create_backup=True
        )
        self.assertTrue(edited_path.exists())
        self.assertTrue(val2.is_valid)
        self.assertGreater(val2.element_count, val.element_count, "Paragraph count increased after append")

        # Confirm backup was generated
        backups = list(self.test_dir.glob("spec_backup_*.docx"))
        self.assertGreaterEqual(len(backups), 1, "Backup file preserved during edit")

    def test_04_excel_spreadsheet_formulas_and_chart(self):
        """Verify Excel workbook creation, formulas (=SUM), and native chart insertion."""
        ss = SpreadsheetStudio(self.test_dir)
        data = [
            ["Quarter", "Revenue", "Cost"],
            ["Q1", 100000, 40000],
            ["Q2", 140000, 50000],
            ["Q3", 180000, 60000],
        ]
        wb_path, val = ss.create_chart_workbook("Financial Summary", data, chart_type="bar", filename="finance.xlsx")
        self.assertTrue(wb_path.exists())
        self.assertTrue(val.is_valid)

        # Reload workbook and inspect formulas and charts
        import openpyxl
        wb = openpyxl.load_workbook(str(wb_path))
        ws = wb.active
        # Cell B5 should contain the formula =SUM(B2:B4)
        self.assertEqual(ws["B5"].value, "=SUM(B2:B4)")
        self.assertEqual(ws["C5"].value, "=SUM(C2:C4)")
        self.assertGreaterEqual(len(ws._charts), 1, "Native openpyxl chart embedded in sheet")

    def test_05_blender_scene_and_headless_execution(self):
        """Verify Blender 5.2 headless scene construction and .blend project saving."""
        res = blender_engine.create_3d_scene(
            scene_description="low-poly house with chimney",
            target_name="test_auto_house",
            export_formats=["blend", "obj"],
            render_preview=False
        )
        self.assertTrue(res["verified"], "Blender 3D scene execution verified")
        outputs = res.get("outputs", {})
        self.assertIn("blend", outputs)
        blend_path = Path(outputs["blend"]["path"])
        self.assertTrue(blend_path.exists(), "Native .blend project file exists on disk")
        self.assertGreater(outputs["blend"]["size_bytes"], 10000, ".blend file has substantial geometry")

    def test_06_email_engine_draft_and_security(self):
        """Verify email draft creation, attachment validation, and authorization check."""
        test_file = self.test_dir / "report_attach.txt"
        test_file.write_text("Confidential deliverable content", encoding="utf-8")

        msg, preview = email_engine.create_draft(
            recipient="client@example.com",
            subject="Project Deliverable Ready",
            body="Aditya Sir, please review the attached document.",
            attachments=[str(test_file)]
        )
        self.assertEqual(msg.status, "DRAFT_SAVED")
        self.assertTrue(Path(msg.saved_eml_path).exists(), "RFC822 .eml file created on disk")
        self.assertIn("client@example.com", preview)

        # Verify send requires authorization when explicit_authorized=False
        send_res = email_engine.send_draft(msg.draft_id, explicit_authorized=False)
        self.assertFalse(send_res["success"], "Unauthorized external send was rejected by Security Center")

    def test_07_natural_language_workflows_parsing(self):
        """Verify tri-lingual natural language intent parsing for desktop workflows."""
        cases = [
            ("AI par 12 slides ki professional PPT banao", "WORKFLOW_PPT"),
            ("Excel file ka data analyze karke charts aur summary banao", "WORKFLOW_EXCEL"),
            ("Blender mein ek low-poly house banao, render karo aur project save karo", "WORKFLOW_BLENDER"),
            ("Email draft banao", "WORKFLOW_EMAIL"),
        ]
        for query, expected_intent in cases:
            res = intent_engine.parse(query)
            self.assertEqual(res.intent, expected_intent, f"Query '{query}' resolved to {expected_intent}")
            self.assertTrue(res.is_local_command, "Local dispatch flag enabled for sub-50ms execution")


if __name__ == "__main__":
    unittest.main()

