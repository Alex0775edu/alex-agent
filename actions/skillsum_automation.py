"""
actions/skillsum_automation.py — SkillSum Business Automation for Resume & Candidate Skills Evaluation.

Capabilities:
  • Local, privacy-first PDF resume text extraction.
  • Evidence-based skills extraction with exact supporting text snippets.
  • Job requirement parsing (required vs. preferred skills).
  • Transparent heuristic candidate matching without automated hiring judgment.
  • Markdown and JSON deliverable export to memory/artifacts/skillsum/.
  • Strict privacy: 100% offline processing; PII is redacted in audit logs.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX 4.0
"""

from __future__ import annotations

import json
import html
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.action_timeline import timeline
from core.security import OWNER_ADDRESS
from creation_studio.pdf_intelligence import PdfIntelligenceEngine

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLSUM_ARTIFACTS_DIR = BASE_DIR / "memory" / "artifacts" / "skillsum"

# Common Technical & Professional Skills Taxonomy (Normalized)
COMMON_SKILLS_MAP = {
    "python": "Python",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "vue": "Vue.js",
    "angular": "Angular",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "google cloud": "GCP",
    "git": "Git",
    "linux": "Linux",
    "c++": "C++",
    "cpp": "C++",
    "java": "Java",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "rest api": "REST API",
    "restful api": "REST API",
    "graphql": "GraphQL",
    "html": "HTML",
    "css": "CSS",
    "tailwind": "Tailwind CSS",
    "agile": "Agile",
    "scrum": "Scrum",
    "project management": "Project Management",
    "ci/cd": "CI/CD",
}


@dataclass
class CandidateProfile:
    candidate_name: str
    email: str
    phone: str
    education: List[str]
    experience_years_detected: Optional[float]
    detected_skills: List[str]
    evidence_snippets: Dict[str, str]
    uncertainty_notes: List[str] = field(default_factory=list)
    raw_word_count: int = 0
    source_text: str = field(default="", repr=False, compare=False)


@dataclass
class JobRequirement:
    title: str
    required_skills: List[str]
    preferred_skills: List[str]
    min_experience_years: Optional[float] = None
    raw_description: str = ""


@dataclass
class SkillMatchEvaluation:
    match_score_pct: Optional[float]
    score_explanation: str
    required_matches: List[Dict[str, str]]
    required_missing: List[str]
    preferred_matches: List[Dict[str, str]]
    preferred_missing: List[str]
    evaluation_notes: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Preliminary decision-support estimate based solely on verifiable resume keywords. "
        "Not an automated hiring decision, qualification guarantee, or definitive ranking."
    )


@dataclass
class SkillSumReport:
    report_id: str
    candidate: CandidateProfile
    job: JobRequirement
    evaluation: SkillMatchEvaluation
    markdown_path: str
    json_path: str
    timestamp: str
    success: bool = True
    error_message: str = ""


class SkillSumAutomation:
    """Core business automation engine for resume parsing and candidate skills evaluation."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        allowed_resume_roots: Optional[List[str | Path]] = None,
    ):
        self.output_dir = Path(output_dir or SKILLSUM_ARTIFACTS_DIR).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        roots = allowed_resume_roots
        if roots is None:
            user_home = Path.home()
            roots = [
                SKILLSUM_ARTIFACTS_DIR,
                user_home / "Documents",
                user_home / "Downloads",
                user_home / "Desktop",
            ]
        self.allowed_resume_roots = tuple(
            Path(root).expanduser().resolve() for root in roots
        )
        self.pdf_engine = PdfIntelligenceEngine(output_dir=self.output_dir)

    # ── 1. Document Extraction ────────────────────────────────────────────────

    def extract_resume_text(self, file_path: str | Path) -> Dict[str, Any]:
        """Validates file format and extracts text using local PDF engine.

        Supports PDF files natively, with safe TXT fallback for tests.
        """
        try:
            p = Path(file_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            return {"error": "Resume file not found or inaccessible.", "is_valid": False}

        if not p.is_file():
            return {"error": "Resume path is not a file.", "is_valid": False}

        if not any(self._path_is_within(p, root) for root in self.allowed_resume_roots):
            return {"error": "Resume path is outside the allowed directories.", "is_valid": False}

        suffix = p.suffix.lower()
        if suffix not in (".pdf", ".txt"):
            return {
                "error": f"Unsupported file format '{suffix}'. Supported formats: PDF (.pdf), Text (.txt).",
                "is_valid": False,
            }

        if suffix == ".pdf":
            result = self.pdf_engine.extract_text_and_meta(p)
            if result.get("error"):
                return {"error": result["error"], "is_valid": False}
            if not result.get("full_text", "").strip():
                return {"error": "Resume PDF contains no extractable text.", "is_valid": False}
            return {
                "is_valid": True,
                "file_name": p.name,
                "full_text": result.get("full_text", ""),
                "pages_count": result.get("pages_count", 0),
                "word_count": result.get("word_count", 0),
            }

        # Plain text fallback
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                return {"error": "Text resume file is empty.", "is_valid": False}
            return {
                "is_valid": True,
                "file_name": p.name,
                "full_text": text,
                "pages_count": 1,
                "word_count": len(text.split()),
            }
        except Exception:
            return {"error": "Could not read text file.", "is_valid": False}

    @staticmethod
    def _path_is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    # ── 2. Candidate Information & Skills Extraction ──────────────────────────

    def parse_candidate_profile(self, resume_text: str) -> CandidateProfile:
        """Extracts candidate profile details while preserving explicit uncertainty.

        Never hallucinates names, degrees, or qualifications.
        """
        uncertainties: List[str] = []
        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]

        # 1. Contact Information
        email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", resume_text)
        email = email_match.group(0) if email_match else "Unknown / Not Specified"
        if email == "Unknown / Not Specified":
            uncertainties.append("Email address not explicitly detected.")

        phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", resume_text)
        phone = phone_match.group(0) if phone_match else "Unknown / Not Specified"
        if phone == "Unknown / Not Specified":
            uncertainties.append("Phone number not explicitly detected.")

        # 2. Candidate Name (Explicit name label, then conservative first-line heuristic)
        candidate_name = "Unknown / Not Specified"
        explicit_name = re.search(
            r"^\s*(?:candidate\s+)?(?:full\s+)?name\s*:\s*([^\r\n]{2,60})\s*$",
            resume_text,
            re.IGNORECASE | re.MULTILINE,
        )
        if explicit_name:
            explicit_value = re.sub(r"[^a-zA-Z\s'-]", "", explicit_name.group(1)).strip()
            if 1 <= len(explicit_value.split()) <= 4:
                candidate_name = explicit_value

        non_name_terms = {
            "resume", "curriculum", "vitae", "profile", "contact", "developer",
            "engineer", "professional", "candidate", "consultant", "analyst",
            "manager", "architect", "designer", "student", "experienced",
            "senior", "junior", "software", "backend", "frontend", "fullstack",
            "project", "projects", "skill", "skills", "competencies", "technical",
            "education", "experience", "summary", "objective", "scientist",
            "administrator", "specialist", "lead", "director", "intern", "employment",
        }
        if candidate_name == "Unknown / Not Specified":
            for line in lines[:5]:
                if ":" in line:
                    continue
                clean_l = re.sub(r"[^a-zA-Z\s'-]", "", line).strip()
                words = clean_l.split()
                if 2 <= len(words) <= 4 and not any(
                    word.lower() in non_name_terms for word in words
                ):
                    candidate_name = clean_l
                    break
        if candidate_name == "Unknown / Not Specified":
            uncertainties.append("Candidate name could not be reliably determined.")

        # 3. Education Extraction (Only if explicitly mentioned)
        education: List[str] = []
        edu_pattern = re.compile(
            r"(?<!\w)(?:bachelor|master|ph\.?d\.?|b\.tech|m\.tech|b\.sc|m\.sc|b\.e|m\.e|degree)(?!\w)",
            re.IGNORECASE,
        )
        for line in lines:
            line_lower = line.lower()
            explicit_education_heading = bool(
                re.match(r"^(?:education|academic background|qualification)s?\s*:", line_lower)
            )
            named_institution = bool(
                re.search(r"\b(?:graduated from|university of|institute of|college of)\b", line_lower)
            )
            if (edu_pattern.search(line) or explicit_education_heading or named_institution) and len(line) < 120:
                education.append(line)
        if not education:
            uncertainties.append("Formal education degrees not explicitly identified.")

        # 4. Years of Experience (Explicit mention only)
        exp_years: Optional[float] = None
        exp_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience", resume_text, re.IGNORECASE)
        if exp_match:
            try:
                exp_years = float(exp_match.group(1))
            except ValueError:
                exp_years = None
        else:
            uncertainties.append("Total years of experience not explicitly stated.")

        # 5. Skills Extraction with Exact Line Evidence
        detected_skills, evidence_snippets = self._extract_skills_with_evidence(resume_text)
        if not detected_skills:
            uncertainties.append("Zero recognized skills matched taxonomy.")

        return CandidateProfile(
            candidate_name=candidate_name,
            email=email,
            phone=phone,
            education=education[:4],
            experience_years_detected=exp_years,
            detected_skills=detected_skills,
            evidence_snippets=evidence_snippets,
            uncertainty_notes=uncertainties,
            raw_word_count=len(resume_text.split()),
            source_text=resume_text,
        )

    def _extract_skills_with_evidence(self, text: str) -> Tuple[List[str], Dict[str, str]]:
        """Extract skills only when the source contains usable positive evidence."""
        detected = set()
        evidence: Dict[str, str] = {}
        lines = text.splitlines()

        for raw_alias, normalized in COMMON_SKILLS_MAP.items():
            pattern = r"(?<!\w)" + re.escape(raw_alias) + r"(?!\w)"
            for line in lines:
                match = next(
                    (
                        candidate
                        for candidate in re.finditer(pattern, line, re.IGNORECASE)
                        if not self._is_negated_skill_mention(
                            line, candidate.start(), candidate.end()
                        )
                        and self._has_positive_skill_context(
                            normalized, raw_alias, line, candidate
                        )
                    ),
                    None,
                )
                if not match:
                    continue
                detected.add(normalized)
                if normalized not in evidence:
                    evidence[normalized] = self._evidence_window(line, match)

        return sorted(list(detected)), evidence

    @staticmethod
    def _is_negated_skill_mention(
        line: str,
        match_start: int,
        match_end: Optional[int] = None,
    ) -> bool:
        prefix = re.split(r"[,;.!?]\s*", line[:match_start].lower())[-1].strip()
        suffix = line[match_end if match_end is not None else match_start:].lower()
        if re.search(
            r"^\s*(?:[-â€”]\s*free|(?:is|was|are|were)\s+not\s+"
            r"(?:used|supported|available|required|included))\b",
            suffix,
        ):
            return True
        if re.search(
            r"\b(?:no|without|lack(?:s|ing)?)\b(?!.*\b(?:but|however|except)\b).*$",
            prefix,
        ):
            return True
        negation_patterns = (
            r"\b(?:no|without|lack(?:s|ing)?)$",
            r"\b(?:no|without|lack(?:s|ing)?)\s+(?:(?:hands[- ]on|prior|professional|work|relevant|any)\s+)*(?:(?:experience|proficiency|familiarity|knowledge|skills?|exposure|background)\s+(?:with|in|using|of)\s*)?$",
            r"\b(?:not|never)\s+(?:(?:familiar|proficient|experienced|skilled|comfortable|knowledgeable|used|able\s+to\s+use)\s+)*(?:(?:with|in|using|of)\s*)?$",
            r"\b(?:do\s+not|does\s+not|did\s+not|don't|doesn't|didn't)\s+(?:currently\s+)?(?:know|use|have|work\s+with)(?:\s+experience)?$",
        )
        return any(re.search(pattern, prefix) for pattern in negation_patterns)

    @staticmethod
    def _has_positive_skill_context(
        normalized: str,
        raw_alias: str,
        line: str,
        match: re.Match[str],
    ) -> bool:
        if normalized not in {"Go", "React", "Rust"} or raw_alias.lower() in {
            "golang", "reactjs", "react.js"
        }:
            return True

        if re.match(
            r"^\s*(?:[-*•]\s*)?(?:(?:key|technical|core|programming)\s+)?"
            r"(?:skills?|competencies|expertise|tech(?:nical)?\s*stack|languages?)\s*[:\-]",
            line,
            re.IGNORECASE,
        ):
            return True

        prefix = line[max(0, match.start() - 60):match.start()].lower()
        suffix = line[match.end():match.end() + 60].lower()
        if re.search(
            r"\b(?:using|used|with|in|written in|built with|developed in|"
            r"programmed in|experience with|expertise in|proficient in)\s*$",
            prefix,
        ):
            return True
        return bool(
            re.match(
                r"\s*(?:language|programming|developer|engineer|framework|"
                r"component|hooks|native|golang|application|backend|frontend)\b",
                suffix,
            )
        )

    @staticmethod
    def _evidence_window(line: str, match: re.Match[str]) -> str:
        max_length = 180
        start = max(0, match.start() - (max_length - len(match.group(0))) // 2)
        end = min(len(line), start + max_length)
        if end - start < max_length:
            start = max(0, end - max_length)
        if match.end() > end:
            end = match.end()
            start = max(0, end - max_length)
        return line[start:end].strip()

    @staticmethod
    def _evidence_supports_skill(skill: str, evidence: str) -> bool:
        for alias, normalized in COMMON_SKILLS_MAP.items():
            if normalized != skill:
                continue
            match = re.search(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                evidence,
                re.IGNORECASE,
            )
            if match and not SkillSumAutomation._is_negated_skill_mention(
                evidence, match.start(), match.end()
            ):
                if SkillSumAutomation._has_positive_skill_context(skill, alias, evidence, match):
                    return True
        return False

    @staticmethod
    def _evidence_is_supported_by_source(skill: str, evidence: str, source_text: str) -> bool:
        if not source_text or not evidence or evidence not in source_text:
            return False
        if SkillSumAutomation._evidence_supports_skill(skill, evidence):
            return True
        return any(
            evidence in line and SkillSumAutomation._evidence_supports_skill(skill, line)
            for line in source_text.splitlines()
        )

    # ── 3. Job Description Parsing ────────────────────────────────────────────

    def parse_job_description(self, jd_input: str | Dict[str, Any]) -> JobRequirement:
        """Parses job requirements into structured required and preferred skills."""
        if isinstance(jd_input, dict):
            required_skills = self._normalize_skill_list(jd_input.get("required_skills", []))
            preferred_skills = [
                skill
                for skill in self._normalize_skill_list(jd_input.get("preferred_skills", []))
                if skill not in required_skills
            ]
            return JobRequirement(
                title=jd_input.get("title", "Target Role"),
                required_skills=required_skills,
                preferred_skills=preferred_skills,
                min_experience_years=jd_input.get("min_experience_years"),
                raw_description=jd_input.get("raw_description", ""),
            )

        raw = str(jd_input)
        title = "Target Position"
        required: Set[str] = set()
        preferred: Set[str] = set()

        # Check for section markers
        req_section = ""
        pref_section = ""
        lower = raw.lower()

        if "preferred" in lower or "nice to have" in lower or "plus" in lower:
            parts = re.split(r"(?:preferred|nice to have|plus|bonus):?", raw, flags=re.IGNORECASE)
            req_section = parts[0]
            pref_section = " ".join(parts[1:])
        else:
            req_section = raw

        # Extract skills for each section
        for raw_alias, normalized in COMMON_SKILLS_MAP.items():
            pattern = r"(?<!\w)" + re.escape(raw_alias) + r"(?!\w)"
            if re.search(pattern, req_section, re.IGNORECASE):
                required.add(normalized)
            elif pref_section and re.search(pattern, pref_section, re.IGNORECASE):
                preferred.add(normalized)

        # Experience detection
        exp_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", raw, re.IGNORECASE)
        min_exp = float(exp_match.group(1)) if exp_match else None

        return JobRequirement(
            title=title,
            required_skills=sorted(list(required)),
            preferred_skills=sorted(list(preferred)),
            min_experience_years=min_exp,
            raw_description=raw[:500],
        )

    def _normalize_skill(self, skill: str) -> str:
        if not isinstance(skill, str):
            return ""
        clean_skill = skill.strip()
        return COMMON_SKILLS_MAP.get(clean_skill.lower(), clean_skill)

    def _normalize_skill_list(self, skills: Any) -> List[str]:
        if isinstance(skills, str):
            values = [skills]
        elif isinstance(skills, (list, tuple, set)):
            values = skills
        else:
            values = []
        return list(dict.fromkeys(
            normalized
            for value in values
            if (normalized := self._normalize_skill(value))
        ))

    # ── 4. Evidence-Based Match Evaluation ────────────────────────────────────

    def evaluate_candidate_match(
        self,
        candidate: CandidateProfile,
        job: JobRequirement
    ) -> SkillMatchEvaluation:
        """Evaluates candidate fit against job requirements with explicit evidence snippets.

        Scoring formula is transparent, heuristic, and never makes protected-class
        assumptions.
        """
        req_matches: List[Dict[str, str]] = []
        req_missing: List[str] = []
        pref_matches: List[Dict[str, str]] = []
        pref_missing: List[str] = []
        notes: List[str] = []

        required_skills = self._normalize_skill_list(job.required_skills)
        preferred_skills = [
            skill
            for skill in self._normalize_skill_list(job.preferred_skills)
            if skill not in required_skills
        ]
        candidate_evidence = {
            skill: evidence
            for skill, evidence in candidate.evidence_snippets.items()
            if skill in candidate.detected_skills
            and isinstance(evidence, str)
            and evidence.strip()
            and self._evidence_is_supported_by_source(
                skill, evidence, candidate.source_text
            )
        }
        candidate_skill_set = set(candidate_evidence)
        if set(candidate.detected_skills) - candidate_skill_set:
            notes.append(
                "Some detected skill keywords lacked positive, verifiable evidence and were not matched."
            )

        # 1. Required skills evaluation
        for s in required_skills:
            if s in candidate_skill_set:
                req_matches.append({
                    "skill": s,
                    "evidence": candidate_evidence[s],
                })
            else:
                req_missing.append(s)

        # 2. Preferred skills evaluation
        for s in preferred_skills:
            if s in candidate_skill_set:
                pref_matches.append({
                    "skill": s,
                    "evidence": candidate_evidence[s],
                })
            else:
                pref_missing.append(s)

        # 3. Transparent Heuristic Scoring Calculation
        # Default weighting: 75% required skills, 25% preferred skills
        total_req = len(required_skills)
        total_pref = len(preferred_skills)

        if total_req == 0 and total_pref == 0:
            score = None
            explanation = "No required or preferred skills were supplied; no match score was calculated."
        elif total_pref == 0:
            unrounded_score = (len(req_matches) / total_req) * 100.0
            score = float(Decimal(str(unrounded_score)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            explanation = (
                f"Heuristic skill estimate: {len(req_matches)}/{total_req} required skills "
                f"= {unrounded_score:.2f}%; displayed score rounded to {score:.1f}%."
            )
        elif total_req == 0:
            unrounded_score = (len(pref_matches) / total_pref) * 100.0
            score = float(Decimal(str(unrounded_score)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            explanation = (
                f"Heuristic skill estimate: {len(pref_matches)}/{total_pref} preferred skills "
                f"= {unrounded_score:.2f}%; displayed score rounded to {score:.1f}%."
            )
        else:
            req_part = (len(req_matches) / total_req) * 75.0
            pref_part = (len(pref_matches) / total_pref) * 25.0
            unrounded_score = req_part + pref_part
            score = float(Decimal(str(unrounded_score)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            explanation = (
                f"Heuristic skill estimate: {len(req_matches)}/{total_req} required contributes "
                f"{req_part:.2f} points + {len(pref_matches)}/{total_pref} preferred contributes "
                f"{pref_part:.2f} points = {unrounded_score:.2f}%; displayed score rounded to {score:.1f}%."
            )

        # Experience check
        if job.min_experience_years is not None:
            if candidate.experience_years_detected is not None:
                if candidate.experience_years_detected >= job.min_experience_years:
                    notes.append(
                        f"Experience meets criteria: {candidate.experience_years_detected} yrs >= {job.min_experience_years} yrs."
                    )
                else:
                    notes.append(
                        f"Experience below requested: {candidate.experience_years_detected} yrs < {job.min_experience_years} yrs."
                    )
            else:
                notes.append(f"Target experience is {job.min_experience_years} yrs, but resume duration was unverified.")

        return SkillMatchEvaluation(
            match_score_pct=score,
            score_explanation=explanation,
            required_matches=req_matches,
            required_missing=req_missing,
            preferred_matches=pref_matches,
            preferred_missing=pref_missing,
            evaluation_notes=notes,
        )

    # ── 5. Report Generation & Export ─────────────────────────────────────────

    @staticmethod
    def _markdown_value(value: Any) -> str:
        text = " ".join(str(value).splitlines())
        escaped_markdown = re.sub(
            r"([\\`*_{}\[\]()#+\-.!|>])",
            r"\\\1",
            text,
        )
        return html.escape(escaped_markdown, quote=False)

    def generate_and_export_report(
        self,
        candidate: CandidateProfile,
        job: JobRequirement,
        evaluation: SkillMatchEvaluation
    ) -> SkillSumReport:
        """Generates structured Markdown and JSON reports in memory/artifacts/skillsum/."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        required_total = len(evaluation.required_matches) + len(evaluation.required_missing)
        preferred_total = len(evaluation.preferred_matches) + len(evaluation.preferred_missing)
        score_label = (
            f"{evaluation.match_score_pct:.1f}%"
            if evaluation.match_score_pct is not None
            else "Not calculated"
        )
        score_context = (
            "Decision-Support Estimate"
            if evaluation.match_score_pct is not None
            else "No requirements supplied"
        )

        # 1. Build Markdown Report
        md_content = f"""# SkillSum Candidate Evaluation Report
- **Report ID:** `SKILLSUM_REPORT_ID_PLACEHOLDER`
- **Candidate:** {self._markdown_value(candidate.candidate_name)}
- **Target Position:** {self._markdown_value(job.title)}
- **Generated At:** {generated_at}
- **Salutation:** {OWNER_ADDRESS}

---

## 1. Executive Summary & Match Score
* **Match Score:** **SKILLSUM_SCORE_LABEL_PLACEHOLDER** (SKILLSUM_SCORE_CONTEXT_PLACEHOLDER)
* **Score Explanation:** {self._markdown_value(evaluation.score_explanation)}
* **Word Count:** {candidate.raw_word_count} words
* **Detected Skills:** {self._markdown_value(', '.join(candidate.detected_skills) if candidate.detected_skills else 'None recognized')}

> [!NOTE]
> {self._markdown_value(evaluation.disclaimer)}

---

## 2. Evidence-Based Skill Alignment

### Matched Required Skills ({len(evaluation.required_matches)} / SKILLSUM_REQUIRED_TOTAL_PLACEHOLDER)
"""
        md_content = md_content.replace("SKILLSUM_SCORE_LABEL_PLACEHOLDER", self._markdown_value(score_label))
        md_content = md_content.replace("SKILLSUM_SCORE_CONTEXT_PLACEHOLDER", score_context)
        md_content = md_content.replace("SKILLSUM_REQUIRED_TOTAL_PLACEHOLDER", str(required_total))

        if evaluation.required_matches:
            for item in evaluation.required_matches:
                md_content += (
                    f"- **{self._markdown_value(item['skill'])}**: "
                    f"*\"{self._markdown_value(item['evidence'])}\"*\n"
                )
        else:
            md_content += "- None matched.\n"

        md_content += f"\n### ❌ Missing Required Skills ({len(evaluation.required_missing)})\n"
        if evaluation.required_missing:
            for s in evaluation.required_missing:
                md_content += f"- {self._markdown_value(s)}\n"
        else:
            md_content += "- None. All required skills verified in resume.\n"

        if preferred_total:
            md_content += f"\n### Preferred / Bonus Skills Matched ({len(evaluation.preferred_matches)} / {preferred_total})\n"
            if evaluation.preferred_matches:
                for item in evaluation.preferred_matches:
                    md_content += (
                        f"- **{self._markdown_value(item['skill'])}**: "
                        f"*\"{self._markdown_value(item['evidence'])}\"*\n"
                    )
            else:
                md_content += "- No preferred skills detected.\n"

        md_content += f"""
---

## 3. Candidate Profile Details
* **Contact Email:** {self._markdown_value(candidate.email)}
* **Contact Phone:** {self._markdown_value(candidate.phone)}
* **Education Mentioned:** {self._markdown_value('; '.join(candidate.education) if candidate.education else 'Not explicitly specified')}
* **Years of Experience:** {candidate.experience_years_detected if candidate.experience_years_detected is not None else 'Uncertain / Not explicitly stated'}

### ⚠️ Uncertainties & Observations
"""
        if candidate.uncertainty_notes:
            for note in candidate.uncertainty_notes:
                md_content += f"- {self._markdown_value(note)}\n"
        else:
            md_content += "- Zero profile anomalies detected.\n"

        if evaluation.evaluation_notes:
            md_content += "\n### 📌 Evaluation Notes:\n"
            for note in evaluation.evaluation_notes:
                md_content += f"- {self._markdown_value(note)}\n"

        json_data: Dict[str, Any]
        created_paths: List[Path] = []
        for _ in range(10):
            token = uuid.uuid4().hex
            report_id = f"SKILLSUM_{timestamp}_{token}"
            md_filename = f"skillsum_report_{timestamp}_{token}.md"
            json_filename = f"skillsum_report_{timestamp}_{token}.json"
            md_path = self.output_dir / md_filename
            json_path = self.output_dir / json_filename
            if md_path.exists() or json_path.exists():
                continue

            md_report = md_content.replace("SKILLSUM_REPORT_ID_PLACEHOLDER", report_id)
            md_report += (
                "\n---\n*Report archived in SkillSum Memory Artifacts: "
                f"`{self._markdown_value(md_path.resolve())}`*\n"
            )
            json_data = {
                "report_id": report_id,
                "timestamp": generated_at,
                "candidate": {
                    key: value
                    for key, value in asdict(candidate).items()
                    if key != "source_text"
                },
                "job": asdict(job),
                "evaluation": asdict(evaluation),
                "markdown_path": str(md_path.resolve()),
                "json_path": str(json_path.resolve()),
            }
            created_paths = []
            try:
                with md_path.open("x", encoding="utf-8") as handle:
                    created_paths.append(md_path)
                    handle.write(md_report)
                with json_path.open("x", encoding="utf-8") as handle:
                    created_paths.append(json_path)
                    handle.write(json.dumps(json_data, indent=2, ensure_ascii=False))
                break
            except FileExistsError:
                for created_path in created_paths:
                    created_path.unlink(missing_ok=True)
                continue
            except Exception:
                for created_path in created_paths:
                    created_path.unlink(missing_ok=True)
                raise
        else:
            raise FileExistsError("Could not allocate unique SkillSum report filenames.")

        try:
            if not all(path.is_file() and path.stat().st_size > 0 for path in (md_path, json_path)):
                raise OSError("SkillSum report files failed verification.")
        except Exception:
            for created_path in (md_path, json_path):
                try:
                    created_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        try:
            timeline.record(
                "SKILLSUM",
                "SkillSum evaluation completed",
                "Markdown and JSON reports were generated.",
                status="SUCCESS",
            )
        except Exception:
            pass

        return SkillSumReport(
            report_id=report_id,
            candidate=replace(candidate, source_text=""),
            job=job,
            evaluation=evaluation,
            markdown_path=str(md_path.resolve()),
            json_path=str(json_path.resolve()),
            timestamp=json_data["timestamp"],
            success=True,
        )

    # ── 6. Unified Workflow Method ────────────────────────────────────────────

    def process_candidate_resume(
        self,
        resume_path: str | Path,
        job_description: Optional[str | Dict[str, Any]] = None
    ) -> SkillSumReport:
        """Complete end-to-end SkillSum business automation workflow."""
        extracted = self.extract_resume_text(resume_path)
        if not extracted.get("is_valid"):
            err = extracted.get("error", "Unknown extraction failure")
            return SkillSumReport(
                report_id="",
                candidate=CandidateProfile("Unknown", "", "", [], None, [], []),
                job=JobRequirement("Unknown", [], []),
                evaluation=SkillMatchEvaluation(0.0, err, [], [], [], []),
                markdown_path="",
                json_path="",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message=err
            )

        candidate = self.parse_candidate_profile(extracted["full_text"])
        job = self.parse_job_description(
            job_description
            if job_description is not None
            else "General Software Role (Python, SQL, Git)"
        )
        evaluation = self.evaluate_candidate_match(candidate, job)
        try:
            return self.generate_and_export_report(candidate, job, evaluation)
        except Exception:
            try:
                timeline.record(
                    "SKILLSUM",
                    "SkillSum evaluation failed",
                    "Verified report files could not be created.",
                    status="FAILED",
                )
            except Exception:
                pass
            return SkillSumReport(
                report_id="",
                candidate=replace(candidate, source_text=""),
                job=job,
                evaluation=evaluation,
                markdown_path="",
                json_path="",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message="Could not create and verify both SkillSum report files.",
            )


# Global Singleton instance
skillsum_service = SkillSumAutomation()

