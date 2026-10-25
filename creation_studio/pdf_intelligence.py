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


def _get_pdf_reader_writer():
    """Returns (PdfReader, PdfWriter) favoring pypdf, falling back to PyPDF2."""
    try:
        import pypdf
        return pypdf.PdfReader, pypdf.PdfWriter
    except ImportError:
        try:
            import PyPDF2
            return PyPDF2.PdfReader, PyPDF2.PdfWriter
        except ImportError:
            raise ImportError("Neither pypdf nor PyPDF2 is installed in the current environment.")


class PdfIntelligenceEngine:
    """Provides non-destructive PDF analysis, text extraction, splitting,

    merging, and rotation. Preserves original files by default.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_text_and_meta(self, pdf_path: str | Path) -> Dict[str, Any]:
        """Extract text and metadata from PDF without altering source.

        Prefers pdfplumber for high-fidelity extraction and tries the
        compatibility reader if it fails or returns no text.
        """
        try:
            p = Path(pdf_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            return {
                "error": "PDF file not found or inaccessible.",
                "file_name": "",
                "is_valid": False,
                "pages_count": 0,
                "full_text": "",
            }

        if not p.is_file():
            return {
                "error": "PDF path is not a file.",
                "file_name": p.name,
                "is_valid": False,
                "pages_count": 0,
                "full_text": "",
            }

        if p.stat().st_size == 0:
            return {
                "error": "PDF file is empty (0 bytes).",
                "file_name": p.name,
                "is_valid": False,
                "is_empty": True,
                "pages_count": 0,
                "full_text": "",
            }

        # 1. Prefer pdfplumber for rich layout & text extraction
        try:
            import pdfplumber
            with pdfplumber.open(str(p)) as pdf:
                page_texts = []
                for idx, page in enumerate(pdf.pages):
                    txt = page.extract_text() or ""
                    page_texts.append({"page": idx + 1, "text": txt})

                full_text = "\n\n".join(pt["text"] for pt in page_texts).strip()
                meta = {str(k): str(v) for k, v in (pdf.metadata or {}).items()}

                if not full_text:
                    raise ValueError("No text extracted by preferred reader.")

                return {
                    "file_name": p.name,
                    "pages_count": len(pdf.pages),
                    "is_valid": True,
                    "is_encrypted": False,
                    "is_scanned": False,
                    "full_text": full_text,
                    "word_count": len(full_text.split()),
                    "pages": page_texts,
                    "metadata": meta,
                    "engine": "pdfplumber",
                }

        except Exception as plumber_err:
            # Check for encryption errors specifically
            err_str = str(plumber_err).lower()
            if any(marker in err_str for marker in ("password", "encrypt", "decrypt")):
                return {
                    "file_name": p.name,
                    "pages_count": 0,
                    "is_valid": False,
                    "is_encrypted": True,
                    "full_text": "",
                    "metadata": {},
                    "error": "PDF is encrypted and password-protected.",
                }
            # If not encryption, attempt PyPDF2 fallback
            pass

        # 2. Fallback to PyPDF2
        try:
            PdfReader, _ = _get_pdf_reader_writer()
            reader = PdfReader(str(p))
            is_encrypted = getattr(reader, "is_encrypted", None)
            if is_encrypted is None:
                is_encrypted = getattr(reader, "isEncrypted", False)
            if is_encrypted:
                return {
                    "file_name": p.name,
                    "is_valid": False,
                    "is_encrypted": True,
                    "pages_count": 0,
                    "full_text": "",
                    "metadata": {},
                    "error": "PDF is encrypted and password-protected.",
                }

            pages = reader.pages
            if len(pages) == 0:
                return {
                    "file_name": p.name,
                    "is_valid": False,
                    "is_empty": True,
                    "is_encrypted": False,
                    "pages_count": 0,
                    "full_text": "",
                    "word_count": 0,
                    "pages": [],
                    "metadata": {},
                    "error": "PDF contains no pages.",
                }

            page_texts = []
            for idx, page in enumerate(pages):
                txt = page.extract_text() or ""
                page_texts.append({"page": idx + 1, "text": txt})

            full_text = "\n\n".join(pt["text"] for pt in page_texts).strip()
            meta = {str(k): str(v) for k, v in (reader.metadata or {}).items()}

            if not full_text:
                return {
                    "file_name": p.name,
                    "pages_count": len(pages),
                    "is_valid": False,
                    "is_encrypted": False,
                    "is_scanned": True,
                    "full_text": "",
                    "word_count": 0,
                    "pages": page_texts,
                    "metadata": meta,
                    "error": "PDF contains no extractable text (OCR is not supported).",
                }

            return {
                "file_name": p.name,
                "pages_count": len(pages),
                "is_valid": True,
                "is_encrypted": False,
                "is_scanned": False,
                "full_text": full_text,
                "word_count": len(full_text.split()),
                "pages": page_texts,
                "metadata": meta,
                "engine": "PyPDF2",
            }
        except ImportError:
            return {
                "file_name": p.name,
                "error": "No supported PDF library is available.",
                "is_valid": False,
                "pages_count": 0,
                "full_text": "",
            }
        except Exception:
            return {
                "file_name": p.name,
                "error": "Failed to extract PDF; the document is corrupt or unsupported.",
                "is_valid": False,
                "is_corrupt": True,
                "pages_count": 0,
                "full_text": "",
            }

    def split_pdf(self, pdf_path: str | Path, start_page: int, end_page: int) -> Tuple[Path, ValidationResult]:
        """Extract a sub-range of pages into a new PDF file."""
        src = Path(pdf_path).resolve()
        out_name = f"{src.stem}_pages_{start_page}_to_{end_page}.pdf"
        target_path = self.output_dir / out_name

        try:
            PdfReader, PdfWriter = _get_pdf_reader_writer()
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
            PdfReader, PdfWriter = _get_pdf_reader_writer()
            writer = PdfWriter()

            for p_str in pdf_paths:
                p = Path(p_str).resolve()
                if p.exists():
                    writer.append(str(p))

            with open(target_path, "wb") as f:
                writer.write(f)

            size = target_path.stat().st_size
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
