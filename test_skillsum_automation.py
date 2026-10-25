"""
test_skillsum_automation.py — Targeted Verification Suite for SkillSum Business Automation.

Tests:
  1. Valid text-based PDF resume extraction (pdfplumber & PyPDF2 fallback).
  2. Edge cases: Missing file, empty (0-byte) file, corrupt file, image-only/scanned PDF, and unsupported file.
  3. Candidate profile extraction & uncertainty preservation (no invented fields).
  4. Job description parsing into required and preferred skill sets.
  5. Evidence-based matching, exact quote retention, and transparent heuristic scoring.
  6. Deliverable report generation (Markdown & JSON) in memory/artifacts/skillsum/ with path verification.
  7. Regression checks for existing PdfIntelligenceEngine APIs (split_pdf and merge_pdfs).

Owner: Aditya Rajak
Salutation: Sir
"""

import io
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import PyPDF2
from actions.skillsum_automation import (
    CandidateProfile,
    JobRequirement,
    SkillSumAutomation,
    skillsum_service,
)
from creation_studio.pdf_intelligence import PdfIntelligenceEngine


def make_clean_pdf(lines: list[str]) -> bytes:
    """Generates a strictly compliant PDF 1.4 byte sequence with exact xref offsets."""
    stream_lines = ["BT", "/F1 12 Tf", "50 720 Td", "14 TL"]
    for idx, l in enumerate(lines):
        clean = l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx == 0:
            stream_lines.append(f"({clean}) Tj")
        else:
            stream_lines.append(f"T* ({clean}) Tj")
    stream_lines.append("ET")
    stream_content = "\n".join(stream_lines)
    s_bytes = stream_content.encode("latin1")

    obj1 = b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    obj2 = b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    obj3 = (
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
    )
    obj4_header = f"4 0 obj << /Length {len(s_bytes)} >>\nstream\n".encode("latin1")
    obj4_footer = b"\nendstream\nendobj\n"
    obj4 = obj4_header + s_bytes + obj4_footer
    obj5 = b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"

    header = b"%PDF-1.4\n"
    pos1 = len(header)
    pos2 = pos1 + len(obj1)
    pos3 = pos2 + len(obj2)
    pos4 = pos3 + len(obj3)
    pos5 = pos4 + len(obj4)
    xref_pos = pos5 + len(obj5)

    xref = (
        f"xref\n0 6\n0000000000 65535 f \n{pos1:010d} 00000 n \n{pos2:010d} 00000 n \n"
        f"{pos3:010d} 00000 n \n{pos4:010d} 00000 n \n{pos5:010d} 00000 n \n"
        f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin1")

    return header + obj1 + obj2 + obj3 + obj4 + obj5 + xref


def test_1_valid_pdf_extraction(temp_dir: Path):
    print("\n--- TEST 1: Valid Text-Based PDF Extraction ---")
    pdf_bytes = make_clean_pdf([
        "Rohan Gupta",
        "Email: rohan.gupta@example.com",
        "Phone: 912-345-6789",
        "Education: Master of Technology in Software Engineering",
        "Experience: 5 years of experience in backend development",
        "Skills: Python, FastAPI, Docker, PostgreSQL, Redis, Git",
    ])
    sample_pdf = temp_dir / "synthetic_resume_rohan.pdf"
    sample_pdf.write_bytes(pdf_bytes)

    engine = PdfIntelligenceEngine(output_dir=temp_dir)
    res = engine.extract_text_and_meta(sample_pdf)

    assert "error" not in res, f"Expected clean extraction, got error: {res.get('error')}"
    assert res["pages_count"] == 1
    assert "Rohan Gupta" in res["full_text"]
    assert "FastAPI" in res["full_text"]
    assert res["word_count"] > 15
    print(f"  [PASS] Successfully extracted {res['word_count']} words via {res.get('engine', 'pdfplumber')}.")


def test_2_edge_cases_and_error_handling(temp_dir: Path):
    print("\n--- TEST 2: Error Handling (Missing, Empty, Corrupt, Scanned, Unsupported) ---")
    engine = PdfIntelligenceEngine(output_dir=temp_dir)

    # 1. Missing file
    res_missing = engine.extract_text_and_meta(temp_dir / "non_existent_file.pdf")
    assert "error" in res_missing
    assert "not found" in res_missing["error"].lower()
    print("  [PASS] Missing file handled cleanly.")

    # 2. Empty (0-byte) file
    empty_file = temp_dir / "empty.pdf"
    empty_file.write_bytes(b"")
    res_empty = engine.extract_text_and_meta(empty_file)
    assert res_empty.get("is_empty") is True
    assert "empty" in res_empty["error"].lower()
    print("  [PASS] Empty (0-byte) file handled cleanly.")

    # 3. Corrupt file
    corrupt_file = temp_dir / "corrupt.pdf"
    corrupt_file.write_bytes(b"NOT_A_VALID_PDF_STREAM_HEADER")
    res_corrupt = engine.extract_text_and_meta(corrupt_file)
    assert "error" in res_corrupt or res_corrupt.get("is_corrupt") is True
    print("  [PASS] Corrupt PDF handled cleanly.")

    # 4. Scanned / image-only (0 extractable text)
    w = PyPDF2.PdfWriter()
    w.add_blank_page(width=300, height=300)
    blank_pdf = temp_dir / "blank_scanned.pdf"
    with open(blank_pdf, "wb") as f:
        w.write(f)
    res_scanned = engine.extract_text_and_meta(blank_pdf)
    assert res_scanned.get("is_scanned") is True
    assert "no extractable text" in res_scanned.get("error", "").lower()
    print("  [PASS] Image-only/scanned PDF without text stream handled cleanly.")

    # 5. Unsupported format in SkillSum service
    unsupported = temp_dir / "malware.exe"
    unsupported.write_bytes(b"MZ\x90\x00")
    service = SkillSumAutomation(output_dir=temp_dir, allowed_resume_roots=[temp_dir])
    res_unsupported = service.extract_resume_text(unsupported)
    assert not res_unsupported["is_valid"]
    assert "unsupported" in res_unsupported["error"].lower()
    print("  [PASS] Unsupported file extension rejected safely.")


def test_3_profile_extraction_and_uncertainty():
    print("\n--- TEST 3: Candidate Profile Extraction & Uncertainty Preservation ---")
    service = SkillSumAutomation()

    # Case A: Complete details
    text_complete = """
Priya Sen
Email: priya.sen@example.org
Phone: (555) 123-4567
Education: Bachelor of Science in Information Technology
Experience: 3 years of experience in fullstack web engineering
Core Competencies: Python, Django, React, TypeScript, PostgreSQL, Git
"""
    profile_a = service.parse_candidate_profile(text_complete)
    assert profile_a.candidate_name == "Priya Sen"
    assert profile_a.email == "priya.sen@example.org"
    assert profile_a.phone == "(555) 123-4567"
    assert profile_a.experience_years_detected == 3.0
    assert "Python" in profile_a.detected_skills
    assert "React" in profile_a.detected_skills
    assert len(profile_a.uncertainty_notes) == 0

    explicitly_labeled = service.parse_candidate_profile("Name: Synthetic Candidate")
    assert explicitly_labeled.candidate_name == "Synthetic Candidate"
    print("  [PASS] Complete candidate profile extracted accurately.")

    # Case B: Incomplete details (Verify no hallucinations)
    text_incomplete = """
Experienced Developer
Key Skills: C++, Linux, Docker
Projects: High-speed networking engine.
"""
    profile_b = service.parse_candidate_profile(text_incomplete)
    assert profile_b.candidate_name == "Unknown / Not Specified"
    assert profile_b.email == "Unknown / Not Specified"
    assert profile_b.phone == "Unknown / Not Specified"
    assert profile_b.experience_years_detected is None
    assert len(profile_b.uncertainty_notes) >= 3
    assert any("Email" in n for n in profile_b.uncertainty_notes)
    assert any("experience" in n.lower() for n in profile_b.uncertainty_notes)
    print("  [PASS] Incomplete candidate profile preserved explicit uncertainty without inventing data.")


def test_4_and_5_evidence_matching_and_scoring():
    print("\n--- TEST 4 & 5: Evidence-Based Skill Matching & Heuristic Scoring ---")
    service = SkillSumAutomation()

    resume_text = """
Aditya Verma
Email: aditya.verma@example.com
Phone: 999-888-7777
Experience: 4.5 years of experience
Technical Skills:
  - Strong proficiency in Python, FastAPI, and PostgreSQL for microservices.
  - Familiarity with Git for version control and Docker containerization.
"""
    profile = service.parse_candidate_profile(resume_text)
    negative_only = service.parse_candidate_profile(
        "Python is not used; no Python or SQL experience; Rust-free environment; "
        "I do not know Java and I don't use Docker."
    )
    assert "Python" not in negative_only.detected_skills
    assert "SQL" not in negative_only.detected_skills
    assert "Rust" not in negative_only.detected_skills
    assert "Java" not in negative_only.detected_skills
    assert "Docker" not in negative_only.detected_skills

    # Job requirement:
    # Required: Python, FastAPI, PostgreSQL, Kubernetes (3 of 4 match)
    # Preferred: Docker, AWS (1 of 2 match)
    job_req = JobRequirement(
        title="Senior Backend Engineer",
        required_skills=["Python", "FastAPI", "PostgreSQL", "Kubernetes"],
        preferred_skills=["Docker", "AWS"],
        min_experience_years=3.0,
    )

    evaluation = service.evaluate_candidate_match(profile, job_req)

    # 1. Evidence Verification
    matched_req_names = [m["skill"] for m in evaluation.required_matches]
    assert "Python" in matched_req_names
    assert "FastAPI" in matched_req_names
    assert "PostgreSQL" in matched_req_names
    assert "Kubernetes" in evaluation.required_missing

    # Check that exact quotes are retained
    fastapi_match = next(m for m in evaluation.required_matches if m["skill"] == "FastAPI")
    assert "FastAPI" in fastapi_match["evidence"]
    assert "microservices" in fastapi_match["evidence"]

    matched_pref_names = [m["skill"] for m in evaluation.preferred_matches]
    assert "Docker" in matched_pref_names
    assert "AWS" in evaluation.preferred_missing

    # 2. Transparent Heuristic Score Verification:
    # Required: 3/4 = 75% -> 75% of 75 = 56.25%
    # Preferred: 1/2 = 50% -> 50% of 25 = 12.5%
    # Expected Total: 56.25 + 12.5 = 68.75% -> 68.8%
    assert evaluation.match_score_pct == 68.8, f"Expected 68.8%, got {evaluation.match_score_pct}%"
    assert "Heuristic skill estimate" in evaluation.score_explanation
    assert "decision-support estimate" in evaluation.disclaimer.lower()
    print(f"  [PASS] Evidence quotes verified: \"{fastapi_match['evidence']}\"")
    print(f"  [PASS] Transparent heuristic score verified: {evaluation.match_score_pct}% ({evaluation.score_explanation})")


def test_6_report_generation_and_export(temp_dir: Path):
    print("\n--- TEST 6: Report Generation & Deliverable Verification ---")
    service = SkillSumAutomation(output_dir=temp_dir, allowed_resume_roots=[temp_dir])

    pdf_bytes = make_clean_pdf([
        "Sneha Kapoor",
        "Email: sneha.kapoor@example.com",
        "Education: Bachelor of Technology",
        "Experience: 2 years of experience",
        "Skills: React, JavaScript, TypeScript, HTML, CSS, Tailwind",
    ])
    resume_file = temp_dir / "sneha_resume.pdf"
    resume_file.write_bytes(pdf_bytes)

    with patch("actions.skillsum_automation.timeline.record"):
        report = service.process_candidate_resume(
            resume_path=resume_file,
            job_description={
                "title": "Frontend Developer",
                "required_skills": ["React", "TypeScript", "Tailwind"],
                "preferred_skills": ["Vue.js"],
            }
        )

    assert report.success is True, f"Report generation failed: {report.error_message}"
    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()
    assert Path(report.markdown_path).stat().st_size > 200
    assert Path(report.json_path).stat().st_size > 200

    # Validate JSON integrity
    with open(report.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["candidate"]["candidate_name"] == "Sneha Kapoor"
    assert "source_text" not in data["candidate"]
    assert report.candidate.source_text == ""
    assert data["evaluation"]["match_score_pct"] == 75.0  # 3/3 required (75%) + 0/1 preferred (0%) = 75%

    # Validate Markdown content
    md_text = Path(report.markdown_path).read_text(encoding="utf-8")
    assert "SkillSum Candidate Evaluation Report" in md_text
    assert "Sneha Kapoor" in md_text
    assert "Decision-Support Estimate" in md_text
    print(f"  [PASS] Verified Markdown deliverable ({Path(report.markdown_path).stat().st_size} bytes): {report.markdown_path}")
    print(f"  [PASS] Verified JSON deliverable ({Path(report.json_path).stat().st_size} bytes): {report.json_path}")


def test_7_pdf_engine_regression(temp_dir: Path):
    print("\n--- TEST 7: Regression Checks for Existing PDF APIs (Split & Merge) ---")
    engine = PdfIntelligenceEngine(output_dir=temp_dir)

    # Create 2 separate 1-page PDFs
    p1 = temp_dir / "doc1.pdf"
    p2 = temp_dir / "doc2.pdf"
    p1.write_bytes(make_clean_pdf(["Page One Content for Document 1"]))
    p2.write_bytes(make_clean_pdf(["Page Two Content for Document 2"]))

    # 1. Merge
    merged_path, merge_val = engine.merge_pdfs([p1, p2], output_filename="test_merged.pdf")
    assert merge_val.is_valid is True, f"Merge failed: {merge_val.error_message}"
    assert merged_path.exists()
    assert merge_val.element_count == 2

    # 2. Split
    split_path, split_val = engine.split_pdf(merged_path, start_page=1, end_page=1)
    assert split_val.is_valid is True, f"Split failed: {split_val.error_message}"
    assert split_path.exists()
    assert split_val.element_count == 1

    print(f"  [PASS] merge_pdfs verified: {merge_val.element_count} pages merged successfully.")
    print(f"  [PASS] split_pdf verified: {split_val.element_count} page extracted successfully.")


def test_8_dispatch_integration(temp_dir: Path):
    print("\n--- TEST 8: Task Dispatcher Integration ---")
    from core.task_dispatcher import task_dispatcher

    pdf_bytes = make_clean_pdf([
        "Vikram Malhotra",
        "Email: vikram@example.com",
        "Experience: 6 years of experience",
        "Skills: Python, Django, AWS, Docker, Git",
    ])
    resume_file = temp_dir / "vikram_resume.pdf"
    resume_file.write_bytes(pdf_bytes)

    from actions.skillsum_automation import skillsum_service
    original_state = (
        skillsum_service.output_dir,
        skillsum_service.allowed_resume_roots,
        skillsum_service.pdf_engine,
    )
    skillsum_service.output_dir = temp_dir.resolve()
    skillsum_service.allowed_resume_roots = (temp_dir.resolve(),)
    skillsum_service.pdf_engine = PdfIntelligenceEngine(output_dir=temp_dir)
    try:
        with patch("core.task_dispatcher.timeline.record"), patch("actions.skillsum_automation.timeline.record"):
            # Dispatch via skill_name="skillsum", action_name="process_resume"
            res = task_dispatcher.dispatch(
                skill_name="skillsum",
                action_name="process_resume",
                params={
                    "resume_path": str(resume_file),
                    "job_description": "Senior Python Backend Developer (Python, Django, AWS)",
                }
            )
    finally:
        (
            skillsum_service.output_dir,
            skillsum_service.allowed_resume_roots,
            skillsum_service.pdf_engine,
        ) = original_state

    assert res.success is True, f"Dispatch failed: {res.error}"
    assert res.verified is True
    assert "Vikram Malhotra" in res.output
    assert len(res.generated_files) == 2  # Markdown and JSON
    assert all(Path(file_path).is_file() and Path(file_path).stat().st_size > 0 for file_path in res.generated_files)
    print(f"  [PASS] Task dispatcher successfully executed SkillSum workflow: {res.output[:80]}...")


def test_9_intent_routing_and_conversation_fallback(temp_dir: Path):
    print("\n--- TEST 9: Intent Engine Routing & Ordinary Conversation Fallback ---")
    from core.intent_engine import intent_engine

    # 1. SkillSum command routing
    cmd_skillsum = "Alex, evaluate resume C:/Users/test/resume.pdf"
    res_intent = intent_engine.parse(cmd_skillsum)
    assert res_intent.intent == "SKILLSUM_RESUME_EVAL", f"Expected SKILLSUM_RESUME_EVAL, got {res_intent.intent}"
    assert "C:/Users/test/resume.pdf" in res_intent.slots.get("resume_path", "")
    print(f"  [PASS] Intent engine matched SkillSum resume command -> {res_intent.intent} (Slots: {res_intent.slots})")

    # 2. Ordinary conversational request MUST NOT trigger SkillSum
    cmd_conversation = "Alex, what is the meaning of machine learning?"
    res_conv = intent_engine.parse(cmd_conversation)
    assert res_conv.intent != "SKILLSUM_RESUME_EVAL", f"Conversational query was mistakenly routed to SkillSum: {res_conv.intent}"
    print(f"  [PASS] Ordinary conversational query preserved general routing -> {res_conv.intent}")


def test_10_evidence_integrity_and_ambiguous_skills():
    print("\n--- TEST 10: Evidence Integrity, Negation, and Ambiguous Skill Names ---")
    service = SkillSumAutomation()
    long_skills_line = "Skills: " + ("Python, Django, " * 18) + "React, TypeScript"
    resume_text = "\n".join([
        "No experience with Python.",
        "I react quickly to changing requirements.",
        "I go to university every week.",
        "Rust is a durable material.",
        long_skills_line,
        "React is not used in my projects.",
        "I have used React for accessible interfaces.",
    ])
    profile = service.parse_candidate_profile(resume_text)
    assert "Python" in profile.detected_skills  # supported by the later Skills section
    assert "React" in profile.detected_skills
    assert "Go" not in profile.detected_skills
    assert "Rust" not in profile.detected_skills
    react_evidence = profile.evidence_snippets["React"]
    assert "React" in react_evidence
    assert react_evidence in profile.source_text
    assert service._evidence_is_supported_by_source("React", react_evidence, profile.source_text)

    forged = CandidateProfile(
        candidate_name="Synthetic Candidate",
        email="Unknown / Not Specified",
        phone="Unknown / Not Specified",
        education=[],
        experience_years_detected=None,
        detected_skills=["Python"],
        evidence_snippets={"Python": "Skills: Python"},
    )
    evaluation = service.evaluate_candidate_match(
        forged,
        JobRequirement("Engineer", ["Python"], []),
    )
    assert not evaluation.required_matches
    assert evaluation.required_missing == ["Python"]
    print("  [PASS] Negated and ambiguous mentions were rejected; only sourced evidence was matched.")


def test_11_path_authorization_and_private_errors(temp_dir: Path):
    print("\n--- TEST 11: Resume Path Authorization ---")
    allowed_dir = temp_dir / "allowed"
    denied_dir = temp_dir / "private"
    allowed_dir.mkdir()
    denied_dir.mkdir()
    allowed_resume = allowed_dir / "synthetic.txt"
    denied_resume = denied_dir / "synthetic.txt"
    allowed_resume.write_text("Skills: Python", encoding="utf-8")
    denied_resume.write_text("Skills: Python", encoding="utf-8")
    service = SkillSumAutomation(output_dir=temp_dir / "reports", allowed_resume_roots=[allowed_dir])

    assert service.extract_resume_text(allowed_resume)["is_valid"]
    denied = service.extract_resume_text(denied_resume)
    assert not denied["is_valid"]
    assert str(denied_resume) not in denied["error"]
    assert "allowed directories" in denied["error"]
    default_service = SkillSumAutomation(output_dir=temp_dir / "default-reports")
    default_denial = default_service.extract_resume_text(allowed_resume)
    assert not default_denial["is_valid"]
    assert "allowed directories" in default_denial["error"]
    print("  [PASS] Reads stayed within the configured root and denial omitted the source path.")


def test_12_pii_redaction():
    print("\n--- TEST 12: Firewall PII Redaction ---")
    from core.firewall import redact

    sample = "Synthetic: person@example.test, (555) 222-3333, +91 98765 43210, password=SuperSecret123"
    redacted = redact(sample)
    assert "person@example.test" not in redacted
    assert "555" not in redacted and "222-3333" not in redacted
    assert "98765 43210" not in redacted
    assert "SuperSecret123" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    print("  [PASS] Email, phone, and credential values were masked.")


def test_13_safe_reports_and_collision_handling(temp_dir: Path):
    print("\n--- TEST 13: Escaped Reports, JSON Validity, and Collision Safety ---")
    service = SkillSumAutomation(output_dir=temp_dir, allowed_resume_roots=[temp_dir])
    malicious = CandidateProfile(
        candidate_name='<img src=x onerror="alert(1)">',
        email="synthetic@example.test",
        phone="555-444-3333",
        education=["<script>alert(1)</script>"],
        experience_years_detected=None,
        detected_skills=["Python"],
        evidence_snippets={"Python": "Skills: Python & scripting"},
        raw_word_count=4,
    )
    job = JobRequirement("<script>Role</script>", ["Python"], [])
    evaluation = service.evaluate_candidate_match(malicious, job)

    with patch("actions.skillsum_automation.time.strftime", return_value="20261024_120000"), \
            patch("actions.skillsum_automation.timeline.record"):
        first = service.generate_and_export_report(malicious, job, evaluation)
        first_content = Path(first.markdown_path).read_text(encoding="utf-8")
        second = service.generate_and_export_report(malicious, job, evaluation)

        forced_md = temp_dir / "skillsum_report_20261024_120000_forced-collision.md"
        forced_json = temp_dir / "skillsum_report_20261024_120000_forced-collision.json"
        forced_md.write_text("User-owned collision sentinel", encoding="utf-8")
        forced_json.write_text("User-owned JSON sentinel", encoding="utf-8")
        with patch(
            "actions.skillsum_automation.uuid.uuid4",
            side_effect=[SimpleNamespace(hex="forced-collision"), SimpleNamespace(hex="fresh-token")],
        ):
            collision_safe = service.generate_and_export_report(malicious, job, evaluation)

    assert first.success and second.success
    assert first.markdown_path != second.markdown_path
    assert Path(first.markdown_path).read_text(encoding="utf-8") == first_content
    assert "fresh-token" in collision_safe.markdown_path
    assert forced_md.read_text(encoding="utf-8") == "User-owned collision sentinel"
    assert forced_json.read_text(encoding="utf-8") == "User-owned JSON sentinel"
    assert Path(first.markdown_path).is_file() and Path(second.markdown_path).is_file()
    assert "<img" not in first_content.lower() and "<script" not in first_content.lower()
    assert "&lt;img" in first_content.lower()
    assert "&lt;script" in first_content.lower() and "&lt;/script" in first_content.lower()
    assert "SKILLSUM_REPORT_ID_PLACEHOLDER" not in first_content
    first_json = json.loads(Path(first.json_path).read_text(encoding="utf-8"))
    assert first_json["candidate"]["candidate_name"] == malicious.candidate_name
    assert "source_text" not in first_json["candidate"]
    assert Path(first.markdown_path).stat().st_size > 0
    assert Path(first.json_path).stat().st_size > 0

    failed_output = temp_dir / "failed-export"
    failed_service = SkillSumAutomation(output_dir=failed_output, allowed_resume_roots=[temp_dir])
    synthetic_resume = temp_dir / "export-failure.txt"
    synthetic_resume.write_text("Skills: Python", encoding="utf-8")
    with patch("actions.skillsum_automation.json.dumps", side_effect=ValueError("synthetic serialization failure")), \
            patch("actions.skillsum_automation.timeline.record"):
        failed_export = failed_service.process_candidate_resume(synthetic_resume, {"required_skills": ["Python"]})
    assert failed_export.success is False
    assert list(failed_output.glob("skillsum_report_*")) == []
    print("  [PASS] Markdown escaped HTML, JSON parsed, and same-second exports did not overwrite.")


def test_14_pdf_fallback_and_edge_cases(temp_dir: Path):
    print("\n--- TEST 14: PDF Fallback, Encrypted, Zero-Page, and Corrupt PDFs ---")
    engine = PdfIntelligenceEngine(output_dir=temp_dir)
    fallback_pdf = temp_dir / "fallback.pdf"
    fallback_pdf.write_bytes(make_clean_pdf(["Fallback extraction text for synthetic resume."]))

    class EmptyPage:
        def extract_text(self):
            return None

    class EmptyPdf:
        pages = [EmptyPage()]
        metadata = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    with patch("pdfplumber.open", return_value=EmptyPdf()):
        fallback = engine.extract_text_and_meta(fallback_pdf)
    assert "Fallback extraction text" in fallback.get("full_text", "")
    assert fallback.get("is_valid") is True

    encrypted_writer = PyPDF2.PdfWriter()
    encrypted_writer.add_blank_page(width=100, height=100)
    encrypted_writer.encrypt("synthetic-password")
    encrypted_path = temp_dir / "encrypted.pdf"
    with encrypted_path.open("wb") as output:
        encrypted_writer.write(output)
    encrypted = engine.extract_text_and_meta(encrypted_path)
    assert encrypted.get("is_encrypted") is True and encrypted.get("is_valid") is False

    zero_page_path = temp_dir / "zero-pages.pdf"
    with zero_page_path.open("wb") as output:
        PyPDF2.PdfWriter().write(output)
    zero_pages = engine.extract_text_and_meta(zero_page_path)
    assert zero_pages.get("is_valid") is False
    assert zero_pages.get("pages_count") == 0

    corrupt_path = temp_dir / "corrupt-again.pdf"
    corrupt_path.write_bytes(b"not a pdf")
    corrupt = engine.extract_text_and_meta(corrupt_path)
    assert corrupt.get("is_valid") is False and corrupt.get("is_corrupt") is True
    print("  [PASS] Empty preferred extraction fell back; encrypted, zero-page, and corrupt PDFs failed safely.")


def test_15_voice_status_redaction_and_conversation_routing(temp_dir: Path):
    print("\n--- TEST 15: Voice Failure Status, Log Redaction, and Ordinary Routing ---")
    from actions.skillsum_automation import skillsum_service
    from core.voice_pipeline import VoiceToActionPipeline

    original_roots = skillsum_service.allowed_resume_roots
    logs = []
    speech = []
    pipeline = VoiceToActionPipeline()
    pipeline.log_callback = logs.append
    pipeline.speak_callback = speech.append
    private_name = "alex-person@example.test-555-444-3333-missing.pdf"
    missing_path = temp_dir / private_name
    skillsum_service.allowed_resume_roots = (temp_dir.resolve(),)
    events = []
    try:
        with patch("core.voice_pipeline.security_manager.is_locked", return_value=False), \
                patch("core.voice_pipeline.security_manager.touch"), \
                patch("core.voice_pipeline.timeline.record", side_effect=lambda *args, **kwargs: events.append((args, kwargs))):
            result = pipeline.process_text_command(f"Alex, evaluate resume {missing_path}")
    finally:
        skillsum_service.allowed_resume_roots = original_roots

    assert result.intent == "SKILLSUM_RESUME_EVAL"
    assert result.success is False and result.verified is False
    assert str(missing_path) not in "\n".join(logs)
    assert "person@example.test" not in "\n".join(logs)
    assert "555-444-3333" not in "\n".join(logs)
    assert events
    event_details = str(events[0][1].get("details", events[0][0][2] if len(events[0][0]) > 2 else ""))
    assert str(missing_path) not in event_details
    assert "SkillSum resume evaluation requested" in event_details

    with patch("core.voice_pipeline.timeline.record"), \
            patch("core.gemini.call", return_value=SimpleNamespace(text="A resume summarizes work history.")):
        conversational = VoiceToActionPipeline().process_text_command("What is a resume?")
    assert conversational.intent == "GENERAL_QUERY"
    assert conversational.engine_used == "gemini_llm"
    assert conversational.success is True
    print("  [PASS] Failed SkillSum stayed failed and logs hid PII; ordinary resume questions used conversation routing.")


def test_16_dispatch_failure_is_not_verified(temp_dir: Path):
    print("\n--- TEST 16: Dispatcher Failure Reporting ---")
    from actions.skillsum_automation import skillsum_service
    from core.task_dispatcher import task_dispatcher

    original_roots = skillsum_service.allowed_resume_roots
    skillsum_service.allowed_resume_roots = (temp_dir.resolve(),)
    try:
        with patch("core.task_dispatcher.timeline.record"), patch("actions.skillsum_automation.timeline.record"):
            result = task_dispatcher.dispatch(
                "skillsum",
                "skillsum_resume_eval",
                {"resume_path": str(temp_dir / "missing-synthetic.pdf")},
            )
    finally:
        skillsum_service.allowed_resume_roots = original_roots
    assert result.success is False and result.verified is False
    assert "failed" in result.output.lower() or "not found" in result.output.lower()

    markdown = temp_dir / "verified-markdown.md"
    missing_json = temp_dir / "missing-json.json"
    markdown.write_text("verified markdown fixture", encoding="utf-8")
    fake_report = SimpleNamespace(
        success=True,
        candidate=SimpleNamespace(candidate_name="Synthetic Candidate"),
        job=SimpleNamespace(title="Synthetic Role"),
        evaluation=SimpleNamespace(match_score_pct=50.0),
        markdown_path=str(markdown),
        json_path=str(missing_json),
    )
    with patch("core.task_dispatcher.timeline.record"), \
            patch("actions.skillsum_automation.skillsum_service.process_candidate_resume", return_value=fake_report):
        partial = task_dispatcher.dispatch(
            "skillsum",
            "process_resume",
            {"resume_path": str(temp_dir / "synthetic.pdf")},
        )
    assert partial.success is False and partial.verified is False
    assert not partial.generated_files
    print("  [PASS] Dispatcher surfaced the failed SkillSum result without reporting verification.")


def test_17_score_edge_cases():
    print("\n--- TEST 17: Score Deduplication, Rounding, and Zero Requirements ---")
    service = SkillSumAutomation()
    profile = service.parse_candidate_profile("Skills: Python, SQL")

    duplicate_job = service.parse_job_description({
        "title": "Synthetic Engineer",
        "required_skills": ["python", "Python", "SQL"],
        "preferred_skills": ["SQL", "Docker"],
    })
    duplicate_eval = service.evaluate_candidate_match(profile, duplicate_job)
    assert duplicate_job.required_skills == ["Python", "SQL"]
    assert duplicate_job.preferred_skills == ["Docker"]
    assert duplicate_eval.match_score_pct == 75.0

    no_requirements = service.evaluate_candidate_match(
        profile,
        JobRequirement("Unspecified Role", [], []),
    )
    assert no_requirements.match_score_pct is None
    assert "no match score was calculated" in no_requirements.score_explanation.lower()

    half_up = service.evaluate_candidate_match(
        profile,
        JobRequirement("Rounding Role", ["Python", "SQL", "Docker"], ["Git"]),
    )
    assert half_up.match_score_pct == 50.0
    assert "displayed score rounded to 50.0%" in half_up.score_explanation
    print("  [PASS] Duplicate requirements were removed, empty requirements stayed unscored, and rounding was explicit.")


if __name__ == "__main__":
    print("=" * 70)
    print("ALEX 4.0 — SKILLSUM AUTOMATION VERIFICATION SUITE")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as td:
        temp_path = Path(td)
        test_1_valid_pdf_extraction(temp_path)
        test_2_edge_cases_and_error_handling(temp_path)
        test_3_profile_extraction_and_uncertainty()
        test_4_and_5_evidence_matching_and_scoring()
        test_6_report_generation_and_export(temp_path)
        test_7_pdf_engine_regression(temp_path)
        test_8_dispatch_integration(temp_path)
        test_9_intent_routing_and_conversation_fallback(temp_path)
        test_10_evidence_integrity_and_ambiguous_skills()
        test_11_path_authorization_and_private_errors(temp_path)
        test_12_pii_redaction()
        test_13_safe_reports_and_collision_handling(temp_path)
        test_14_pdf_fallback_and_edge_cases(temp_path)
        test_15_voice_status_redaction_and_conversation_routing(temp_path)
        test_16_dispatch_failure_is_not_verified(temp_path)
        test_17_score_edge_cases()

    print("\n" + "=" * 70)
    print("ALL 17 SKILLSUM VERIFICATION PHASES PASSED WITH ZERO FAILURES!")
    print("=" * 70)
