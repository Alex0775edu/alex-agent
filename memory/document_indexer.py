"""
memory/document_indexer.py — Intelligent File & Document Knowledge Engine for ALEX 6.0.

Indexes owner-authorized documents into the Knowledge Library:
  • Formats supported: TXT, MD, RST, LOG, Code (.py, .js, .ts, etc.), CSV, TSV, XLSX, DOCX, PDF, PPTX.
  • Respects Central Security Manager workspace boundaries & access control.
  • Chunks documents with overlap & metadata (token estimates, section titles).
  • Change detection via SHA-256 and modification time (skips unchanged, refreshes modified).
  • Stale & missing file detection and automatic cleanup.
  • Bounded retrieval using FTS5 BM25 full-text indexing.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.security import security_manager
from memory.brain_store import brain_store, redact_secrets

CHUNK_SIZE = 800          # Characters per chunk
CHUNK_OVERLAP = 100       # Overlap between contiguous chunks
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB limit per document


class DocumentIndexer:
    """Manages document ingestion, text extraction, semantic chunking, and stale file audits."""

    _instance: Optional[DocumentIndexer] = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> DocumentIndexer:
        if cls._instance is None:
            cls._instance = DocumentIndexer()
        return cls._instance

    def compute_file_hash(self, file_path: Path) -> str:
        """Computes SHA-256 hash of a file for change tracking."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    # ── Text Extraction by Format ─────────────────────────────────────────────

    def extract_text(self, file_path: Path) -> Tuple[str, str]:
        """Extracts plain text and format classification from the given file."""
        ext = file_path.suffix.lower().lstrip(".")
        if ext in ("txt", "md", "rst", "log", "py", "js", "ts", "jsx", "tsx",
                   "html", "css", "json", "yaml", "yml", "toml", "sql", "sh", "bat", "ps1"):
            return self._extract_plain_text(file_path), ext

        if ext in ("csv", "tsv"):
            return self._extract_csv_text(file_path, delimiter="," if ext == "csv" else "\t"), ext

        if ext in ("docx", "doc"):
            return self._extract_docx_text(file_path), ext

        if ext == "pdf":
            return self._extract_pdf_text(file_path), ext

        if ext in ("xlsx", "xls"):
            return self._extract_excel_text(file_path), ext

        if ext in ("pptx", "ppt"):
            return self._extract_pptx_text(file_path), ext

        # Fallback to plain text read
        return self._extract_plain_text(file_path), ext or "unknown"

    def _extract_plain_text(self, file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_csv_text(self, file_path: Path, delimiter: str = ",") -> str:
        lines = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                headers = next(reader, None)
                if headers:
                    lines.append(f"Headers: {', '.join(headers)}")
                for i, row in enumerate(reader):
                    if i < 200:  # Cap at 200 sample rows
                        lines.append(f"Row {i+1}: {', '.join(row)}")
                    else:
                        lines.append(f"... (+ more rows in {file_path.name})")
                        break
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading CSV {file_path.name}: {e}"

    def _extract_docx_text(self, file_path: Path) -> str:
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_txt:
                        paragraphs.append(row_txt)
            return "\n\n".join(paragraphs)
        except Exception:
            # Fallback to plain text search if python-docx fails
            return self._extract_plain_text(file_path)

    def _extract_pdf_text(self, file_path: Path) -> str:
        text = ""
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[:30]:  # Up to 30 pages
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n\n"
            return text
        except Exception:
            pass

        try:
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages[:30]:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n\n"
            return text
        except Exception:
            pass
        return ""

    def _extract_excel_text(self, file_path: Path) -> str:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True)
            lines = []
            for sheet_name in wb.sheetnames[:5]:
                ws = wb[sheet_name]
                lines.append(f"Sheet: {sheet_name}")
                for row in ws.iter_rows(max_row=50, values_only=True):
                    row_vals = [str(v) for v in row if v is not None]
                    if row_vals:
                        lines.append(" | ".join(row_vals))
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading Excel {file_path.name}: {e}"

    def _extract_pptx_text(self, file_path: Path) -> str:
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(file_path, 'r') as z:
                slide_files = [f for f in z.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')]
                slide_files.sort()
                text_parts = []
                for idx, s_name in enumerate(slide_files):
                    xml_content = z.read(s_name)
                    tree = ET.fromstring(xml_content)
                    slide_texts = []
                    for elem in tree.iter():
                        if elem.tag.endswith('}t') and elem.text:
                            slide_texts.append(elem.text)
                    if slide_texts:
                        text_parts.append(f"Slide {idx+1}: " + " ".join(slide_texts))
                return "\n\n".join(text_parts)
        except Exception:
            return ""

    # ── Chunking Logic ────────────────────────────────────────────────────────

    def chunk_text(self, text: str, file_name: str) -> List[Dict[str, Any]]:
        """Splits document text into coherent, overlapping chunks with titles."""
        clean = redact_secrets(text.strip())
        if not clean:
            return []

        # Split into paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        chunks: List[Dict[str, Any]] = []

        current_chunk = ""
        current_title = f"{file_name} Overview"

        for p in paragraphs:
            # Detect section header
            if len(p) < 80 and (p.startswith("#") or p.endswith(":") or p.isupper()):
                if current_chunk:
                    chunks.append({
                        "title": current_title,
                        "content": current_chunk.strip(),
                        "metadata": {"char_len": len(current_chunk)}
                    })
                    current_chunk = ""
                current_title = f"{file_name} — {p.lstrip('#').strip()}"

            if len(current_chunk) + len(p) + 2 <= CHUNK_SIZE:
                current_chunk += ("\n\n" if current_chunk else "") + p
            else:
                if current_chunk:
                    chunks.append({
                        "title": current_title,
                        "content": current_chunk.strip(),
                        "metadata": {"char_len": len(current_chunk)}
                    })
                # If paragraph itself is larger than CHUNK_SIZE, slice it
                if len(p) > CHUNK_SIZE:
                    for i in range(0, len(p), CHUNK_SIZE - CHUNK_OVERLAP):
                        slice_txt = p[i:i + CHUNK_SIZE]
                        chunks.append({
                            "title": f"{current_title} (part {len(chunks)+1})",
                            "content": slice_txt.strip(),
                            "metadata": {"char_len": len(slice_txt)}
                        })
                    current_chunk = ""
                else:
                    current_chunk = p

        if current_chunk:
            chunks.append({
                "title": current_title,
                "content": current_chunk.strip(),
                "metadata": {"char_len": len(current_chunk)}
            })

        return chunks

    # ── Indexing Workflows ────────────────────────────────────────────────────

    def index_file(self, file_path_str: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Indexes a single file after verifying permissions and checking for changes."""
        path = Path(file_path_str).resolve()
        if not path.exists() or not path.is_file():
            return {"status": "error", "message": f"File does not exist: {path}"}

        # Check permission through Central Security Manager
        allowed, perm_reason, _level = security_manager.authorize_file_access(path, "r")
        if not allowed:
            return {"status": "denied", "message": f"Security restriction: {perm_reason}"}

        # Size check
        file_size = path.stat().st_size
        if file_size > MAX_FILE_BYTES:
            return {"status": "skipped", "message": f"File exceeds maximum index size ({file_size} bytes)"}

        # Compute hash
        try:
            f_hash = self.compute_file_hash(path)
        except Exception as e:
            return {"status": "error", "message": f"Could not read file: {e}"}

        # Check existing document record
        existing_docs = brain_store.list_documents()
        existing = next((d for d in existing_docs if d["file_path"] == str(path)), None)
        if existing and existing["file_hash"] == f_hash:
            return {
                "status": "unchanged",
                "doc_id": existing["doc_id"],
                "file_name": path.name,
                "chunks": existing["chunk_count"],
                "message": "File has not changed since last index."
            }

        # Extract and chunk
        text, file_type = self.extract_text(path)
        if not text.strip():
            return {"status": "empty", "message": f"No extractable text found in {path.name}"}

        chunks = self.chunk_text(text, path.name)
        doc_id = brain_store.save_document(
            file_path=str(path),
            file_name=path.name,
            file_type=file_type,
            file_hash=f_hash,
            file_size=file_size,
            chunks=chunks,
            project_id=project_id,
            metadata={"indexed_at": datetime.now().isoformat(), "total_chars": len(text)}
        )

        return {
            "status": "indexed",
            "doc_id": doc_id,
            "file_name": path.name,
            "chunks": len(chunks),
            "message": f"Successfully indexed {len(chunks)} chunks from {path.name}."
        }

    def index_directory(
        self,
        directory_path_str: str,
        project_id: Optional[str] = None,
        max_files: int = 100
    ) -> Dict[str, Any]:
        """Indexes all permitted documents in a workspace directory recursively."""
        root = Path(directory_path_str).resolve()
        if not root.exists() or not root.is_dir():
            return {"status": "error", "message": f"Directory not found: {root}"}

        allowed_exts = {
            ".txt", ".md", ".rst", ".py", ".js", ".ts", ".jsx", ".tsx",
            ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".sql",
            ".csv", ".tsv", ".docx", ".pdf", ".xlsx", ".pptx"
        }
        ignored_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}

        indexed_count = 0
        skipped_count = 0
        unchanged_count = 0
        errors = []

        for p in root.rglob("*"):
            if indexed_count >= max_files:
                break
            if p.is_dir() or any(part in ignored_dirs for part in p.parts):
                continue
            if p.suffix.lower() not in allowed_exts:
                continue

            res = self.index_file(str(p), project_id=project_id)
            if res["status"] == "indexed":
                indexed_count += 1
            elif res["status"] == "unchanged":
                unchanged_count += 1
            elif res["status"] in ("denied", "skipped", "empty"):
                skipped_count += 1
            elif res["status"] == "error":
                errors.append(f"{p.name}: {res.get('message')}")

        return {
            "status": "completed",
            "directory": str(root),
            "indexed_files": indexed_count,
            "unchanged_files": unchanged_count,
            "skipped_files": skipped_count,
            "errors": errors[:5]
        }

    def cleanup_stale_records(self) -> int:
        """Removes indexed records for files that no longer exist on disk."""
        docs = brain_store.list_documents()
        removed = 0
        for d in docs:
            p = Path(d["file_path"])
            if not p.exists():
                brain_store.delete_document(d["doc_id"])
                removed += 1
        return removed


# Singleton Instance
document_indexer = DocumentIndexer.get_instance()
