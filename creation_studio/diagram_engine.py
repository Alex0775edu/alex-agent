"""
creation_studio/diagram_engine.py — Source-Backed Diagram Generator (SVG, Mermaid & HTML).

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from creation_studio.models import OutputFormat, ValidationResult


class DiagramEngine:
    """Generates source-backed, editable visual diagrams:

    - Scalable Vector Graphics (.svg) with clean shapes, text labels, and connection arrows
    - Mermaid (.mmd / markdown) architecture and sequence diagrams
    - Interactive HTML flowchart containers
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_svg_flowchart(
        self,
        title: str,
        steps: List[str | Dict[str, str]],
        filename: Optional[str] = None
    ) -> Tuple[Path, ValidationResult]:
        """Generate a clean, responsive SVG flowchart."""
        clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', title.lower())[:35]}_diagram.svg"
        if not clean_name.endswith(".svg"):
            clean_name += ".svg"
        target_path = self.output_dir / clean_name

        nodes = []
        for idx, item in enumerate(steps):
            if isinstance(item, dict):
                label = item.get("label", f"Step {idx + 1}")
                sub = item.get("sub", "")
            else:
                label = str(item)
                sub = ""
            nodes.append((label, sub))

        # Dynamic SVG layout calculation
        box_width = 240
        box_height = 60
        box_gap = 50
        svg_width = 300
        svg_height = 80 + len(nodes) * (box_height + box_gap)

        svg_lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}">',
            '  <defs>',
            '    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
            '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#0284c7" />',
            '    </marker>',
            '    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%">',
            '      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/>',
            '    </filter>',
            '  </defs>',
            '  <rect width="100%" height="100%" fill="#0b1120"/>',
            f'  <text x="{svg_width/2}" y="35" text-anchor="middle" fill="#38bdf8" font-family="-apple-system, Segoe UI, sans-serif" font-size="16" font-weight="bold">{title}</text>',
        ]

        curr_y = 60
        for i, (label, sub) in enumerate(nodes):
            cx = svg_width / 2
            x = cx - (box_width / 2)
            # Box
            svg_lines.append(f'  <rect x="{x}" y="{curr_y}" width="{box_width}" height="{box_height}" rx="8" fill="#1e293b" stroke="#38bdf8" stroke-width="1.5" filter="url(#shadow)"/>')
            # Text label
            svg_lines.append(f'  <text x="{cx}" y="{curr_y + 32}" text-anchor="middle" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="13" font-weight="600">{label}</text>')
            if sub:
                svg_lines.append(f'  <text x="{cx}" y="{curr_y + 48}" text-anchor="middle" fill="#94a3b8" font-family="Segoe UI, sans-serif" font-size="10">{sub}</text>')

            # Connector arrow to next box
            if i < len(nodes) - 1:
                next_y = curr_y + box_height + box_gap
                svg_lines.append(f'  <line x1="{cx}" y1="{curr_y + box_height}" x2="{cx}" y2="{next_y - 4}" stroke="#0284c7" stroke-width="2" marker-end="url(#arrow)"/>')

            curr_y += box_height + box_gap

        svg_lines.append('</svg>')
        svg_content = "\n".join(svg_lines)
        target_path.write_text(svg_content, encoding="utf-8")

        size = target_path.stat().st_size
        return target_path, ValidationResult(
            is_valid=True,
            file_exists=True,
            file_size_bytes=size,
            format="svg",
            element_count=len(nodes),
            integrity_notes=f"Generated scalable vector diagram ({len(nodes)} connected flowchart nodes)."
        )

    def generate_mermaid_diagram(
        self,
        title: str,
        diagram_type: str = "flowchart TD",  # flowchart TD, sequenceDiagram, erDiagram
        content: str = "",
        filename: Optional[str] = None
    ) -> Tuple[Path, ValidationResult]:
        """Generate an editable Mermaid source document."""
        clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', title.lower())[:35]}.mmd"
        if not clean_name.endswith(".mmd"):
            clean_name += ".mmd"
        target_path = self.output_dir / clean_name

        if not content:
            # Default architecture diagram
            content = (
                f"{diagram_type}\n"
                "    User[Aditya Sir] --> |Command| ALEX[ALEX Agent]\n"
                "    ALEX --> |Authorize| Sec[SecurityManager]\n"
                "    ALEX --> |Dispatch| CS[CreationStudio]\n"
                "    CS --> |Generate| Docs[Documents & PPTX]\n"
                "    CS --> |Process| Media[Images & 3D Assets]\n"
                "    Docs --> |Verify| Out[Outputs & Artifacts]\n"
                "    Media --> |Verify| Out\n"
            )

        target_path.write_text(content, encoding="utf-8")
        size = target_path.stat().st_size

        return target_path, ValidationResult(
            is_valid=True,
            file_exists=True,
            file_size_bytes=size,
            format="mmd",
            element_count=len(content.splitlines()),
            integrity_notes=f"Generated editable Mermaid diagram source ({len(content.splitlines())} lines)."
        )

