"""
creation_studio/pdf_intelligence.py — PDF Intelligence, Text Extraction, Splitting & Merging.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from creation_studio.models import ValidationResult


class PdfIntelligenceEngine:
    """Provides non-destructive PDF analysis, text extraction, splitting,

    merging, and rotation. Preserves original files by default.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_text_and_meta(self, pdf_path: str | Path) -> Dict[str, Any]:
        """Extract text and metadata from PDF without altering source."""
        p = Path(pdf_path).resolve()
        if not p.exists():
            return {"error": f"PDF file not found: {pdf_path}"}

        # Check for pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            if reader.is_encrypted:
                return {
                    "is_encrypted": True,
                    "pages_count": len(reader.pages),
                    "text": "[Encrypted PDF - Password required]",
                    "metadata": {},
                }

            page_texts = []
            for idx, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                page_texts.append({"page": idx + 1, "text": txt})

            full_text = "\n\n".join([pt["text"] for pt in page_texts])
            meta = {k: str(v) for k, v in (reader.metadata or {}).items()}

            return {
                "file_name": p.name,
                "pages_count": len(reader.pages),
                "is_encrypted": False,
                "full_text": full_text,
                "word_count": len(full_text.split()),
                "pages": page_texts,
                "metadata": meta,
            }
        except ImportError:
            # Fallback text scan
            content = p.read_bytes()
            words = len(content.split())
            return {
                "file_name": p.name,
                "pages_count": 1,
                "is_encrypted": False,
                "full_text": f"[pypdf not available; read {len(content)} raw bytes]",
                "word_count": words,
                "metadata": {},
            }
        except Exception as e:
            return {"error": f"Failed to extract PDF: {e}"}

    def split_pdf(self, pdf_path: str | Path, start_page: int, end_page: int) -> Tuple[Path, ValidationResult]:
        """Extract a sub-range of pages into a new PDF file."""
        src = Path(pdf_path).resolve()
        out_name = f"{src.stem}_pages_{start_page}_to_{end_page}.pdf"
        target_path = self.output_dir / out_name

        try:
            from pypdf import PdfReader, PdfWriter
            reader = PdfReader(str(src))
            writer = PdfWriter()

            total_pages = len(reader.pages)
            start_idx = max(0, start_page - 1)
            end_idx = min(total_pages, end_page)

            for i in range(start_idx, end_idx):
                writer.add_page(reader.pages[i])

            with open(target_path, "wb") as f:
                writer.write(f)

            size = target_path.stat().st_size
            return target_path, ValidationResult(
                is_valid=True,
                file_exists=True,
                file_size_bytes=size,
                format="pdf",
                element_count=(end_idx - start_idx),
                integrity_notes=f"Extracted {end_idx - start_idx} pages from {src.name}."
            )
        except Exception as e:
            return target_path, ValidationResult(
                is_valid=False,
                file_exists=target_path.exists(),
                file_size_bytes=0,
                format="pdf",
                error_message=f"Split failed: {e}"
            )

    def merge_pdfs(self, pdf_paths: List[str | Path], output_filename: str = "merged.pdf") -> Tuple[Path, ValidationResult]:
        """Merge multiple PDF documents into a single validated deliverable."""
        target_path = self.output_dir / output_filename
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            total_pages = 0

            for p_str in pdf_paths:
                p = Path(p_str).resolve()
                if p.exists():
                    writer.append(str(p))

            with open(target_path, "wb") as f:
                writer.write(f)

            size = target_path.stat().st_size
            from pypdf import PdfReader
            r = PdfReader(str(target_path))
            total_pages = len(r.pages)

            return target_path, ValidationResult(
                is_valid=True,
                file_exists=True,
                file_size_bytes=size,
                format="pdf",
                element_count=total_pages,
                integrity_notes=f"Merged {len(pdf_paths)} documents into {total_pages} total pages."
            )
        except Exception as e:
            return target_path, ValidationResult(
                is_valid=False,
                file_exists=target_path.exists(),
                file_size_bytes=0,
                format="pdf",
                error_message=f"Merge failed: {e}"
            )

