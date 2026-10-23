"""
creation_studio/models.py — Data models and types for ALEX Multimodal Creation Studio.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AssetType(str, Enum):
    DOCUMENT = "DOCUMENT"
    PRESENTATION = "PRESENTATION"
    SPREADSHEET = "SPREADSHEET"
    IMAGE = "IMAGE"
    DIAGRAM = "DIAGRAM"
    MODEL_3D = "MODEL_3D"
    VIDEO = "VIDEO"


class OutputFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    CSV = "csv"
    TXT = "txt"
    MD = "md"
    HTML = "html"
    JSON = "json"
    SVG = "svg"
    OBJ = "obj"
    STL = "stl"
    PNG = "png"
    JPG = "jpg"
    WEBP = "webp"
    MP4 = "mp4"


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    INSPECTING = "INSPECTING"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ValidationResult:
    """Verification result for a generated or edited asset."""
    is_valid: bool
    file_exists: bool
    file_size_bytes: int
    format: str
    element_count: int = 0  # pages, slides, rows, vertices, duration_s
    integrity_notes: str = ""
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CreationTask:
    """Represents a multimodal creation job in the studio."""
    task_id: str
    user_prompt: str
    asset_type: AssetType
    target_format: OutputFormat
    status: TaskStatus = TaskStatus.QUEUED
    input_files: List[str] = field(default_factory=list)
    output_path: Optional[str] = None
    template_name: Optional[str] = None
    project_name: Optional[str] = None
    validation: Optional[ValidationResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.time()
        return round(end - self.created_at, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["asset_type"] = self.asset_type.value
        d["target_format"] = self.target_format.value
        d["status"] = self.status.value
        d["elapsed_seconds"] = self.elapsed_seconds
        if self.validation:
            d["validation"] = self.validation.to_dict()
        return d


@dataclass
class ToolCapabilityReport:
    """Status report on system tools, compilers, and media engines."""
    blender_available: bool
    blender_path: Optional[str]
    ffmpeg_available: bool
    ffmpeg_path: Optional[str]
    python_docx_available: bool
    python_pptx_available: bool
    openpyxl_available: bool
    pillow_available: bool
    pypdf_available: bool
    reportlab_available: bool
    supported_formats: List[str]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CreationTemplate:
    """Predefined professional templates for documents, slides, and spreadsheets."""
    template_id: str
    name: str
    asset_type: AssetType
    description: str
    default_structure: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["asset_type"] = self.asset_type.value
        return d

