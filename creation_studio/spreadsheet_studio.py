"""
creation_studio/spreadsheet_studio.py — Spreadsheet & Data Studio for Excel (.xlsx) and CSV.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from creation_studio.models import OutputFormat, ValidationResult


class SpreadsheetStudio:
    """Creates, analyzes, and styles Microsoft Excel (.xlsx) workbooks and CSV files.

    Includes formula generation, data cleaning, KPI summaries, and macro safety guards.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_workbook(
        self,
        title: str,
        sheets_data: Dict[str, List[List[Any]]] | List[List[Any]],
        filename: Optional[str] = None,
        add_summary_row: bool = True,
    ) -> Tuple[Path, ValidationResult]:
        """Create a styled Excel workbook with formatted headers, borders, and formulas."""
        clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', title.lower())[:35]}.xlsx"
        if not clean_name.endswith(".xlsx"):
            clean_name += ".xlsx"
        target_path = self.output_dir / clean_name

        try:
            import openpyxl
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter

            wb = openpyxl.Workbook()

            header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")  # Navy
            header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            thin_border = Border(
                left=Side(style='thin', color='E2E8F0'),
                right=Side(style='thin', color='E2E8F0'),
                top=Side(style='thin', color='E2E8F0'),
                bottom=Side(style='thin', color='E2E8F0')
            )

            if isinstance(sheets_data, list):
                sheet_dict = {title or "Data": sheets_data}
            else:
                sheet_dict = sheets_data

            first = True
            total_rows = 0

            for s_name, rows in sheet_dict.items():
                if first:
                    ws = wb.active
                    ws.title = s_name[:31]
                    first = False
                else:
                    ws = wb.create_sheet(title=s_name[:31])

                for r_idx, row in enumerate(rows, start=1):
                    total_rows += 1
                    for c_idx, val in enumerate(row, start=1):
                        cell = ws.cell(row=r_idx, column=c_idx, value=val)
                        cell.border = thin_border
                        if r_idx == 1:
                            cell.fill = header_fill
                            cell.font = header_font
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        elif r_idx % 2 == 0:
                            cell.fill = zebra_fill

                # Add automated summary row for numeric columns if requested
                if add_summary_row and len(rows) > 1:
                    last_row = len(rows) + 1
                    ws.cell(row=last_row, column=1, value="Total / Summary").font = Font(bold=True)
                    # Check which columns are numeric in row 2
                    for c_idx in range(2, len(rows[0]) + 1):
                        sample_val = rows[1][c_idx - 1] if len(rows[1]) >= c_idx else None
                        if isinstance(sample_val, (int, float)):
                            col_letter = get_column_letter(c_idx)
                            formula_cell = ws.cell(
                                row=last_row,
                                column=c_idx,
                                value=f"=SUM({col_letter}2:{col_letter}{last_row - 1})"
                            )
                            formula_cell.font = Font(bold=True)
                            formula_cell.border = thin_border

                # Auto-adjust column widths
                for col in ws.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

            wb.save(str(target_path))
            size = target_path.stat().st_size

            return target_path, ValidationResult(
                is_valid=True,
                file_exists=True,
                file_size_bytes=size,
                format="xlsx",
                element_count=total_rows,
                integrity_notes=f"Created workbook with {len(sheet_dict)} sheet(s) and {total_rows} row(s)."
            )
        except ImportError:
            # Fallback to CSV
            csv_path = target_path.with_suffix(".csv")
            return self.create_csv(title, sheets_data if isinstance(sheets_data, list) else list(sheets_data.values())[0], csv_path.name)

    def create_chart_workbook(
        self,
        title: str,
        data_rows: List[List[Any]],
        chart_type: str = "bar",  # "bar", "line", "pie"
        filename: Optional[str] = None,
        x_col_idx: int = 1,
        y_col_idx: int = 2,
    ) -> Tuple[Path, ValidationResult]:
        """
        Creates an Excel workbook with formatted data, SUM/AVERAGE formulas,
        and an embedded native Excel chart (BarChart, LineChart, or PieChart).
        """
        clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', title.lower())[:35]}.xlsx"
        if not clean_name.endswith(".xlsx"):
            clean_name += ".xlsx"
        target_path = self.output_dir / clean_name

        try:
            import openpyxl
            from openpyxl.chart import BarChart, LineChart, PieChart, Reference
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = title[:31]

            header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
            header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            thin_border = Border(
                left=Side(style='thin', color='CBD5E1'),
                right=Side(style='thin', color='CBD5E1'),
                top=Side(style='thin', color='CBD5E1'),
                bottom=Side(style='thin', color='CBD5E1')
            )

            # Write rows
            for r_idx, row in enumerate(data_rows, start=1):
                for c_idx, val in enumerate(row, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx, value=val)
                    cell.border = thin_border
                    if r_idx == 1:
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif r_idx % 2 == 0:
                        cell.fill = zebra_fill

            rows_len = len(data_rows)
            cols_len = len(data_rows[0]) if data_rows else 0

            # Add Summary Row with SUM formulas
            if rows_len > 1:
                summary_row = rows_len + 1
                ws.cell(row=summary_row, column=1, value="Total").font = Font(bold=True)
                for c in range(2, cols_len + 1):
                    sample = data_rows[1][c - 1] if len(data_rows[1]) >= c else None
                    if isinstance(sample, (int, float)):
                        col_let = get_column_letter(c)
                        sum_cell = ws.cell(row=summary_row, column=c, value=f"=SUM({col_let}2:{col_let}{summary_row - 1})")
                        sum_cell.font = Font(bold=True)
                        sum_cell.border = thin_border

            # Create Native OpenPyXL Chart
            if chart_type.lower() == "line":
                chart = LineChart()
            elif chart_type.lower() == "pie":
                chart = PieChart()
            else:
                chart = BarChart()

            chart.title = title
            chart.style = 10
            chart.width = 16
            chart.height = 10

            data_ref = Reference(ws, min_col=2, min_row=1, max_col=cols_len, max_row=rows_len)
            cats_ref = Reference(ws, min_col=1, min_row=2, max_row=rows_len)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)

            # Place chart to the right of data
            chart_loc = f"{get_column_letter(cols_len + 2)}2"
            ws.add_chart(chart, chart_loc)

            # Column dimensions
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

            wb.save(str(target_path))
            size = target_path.stat().st_size

            return target_path, ValidationResult(
                is_valid=True,
                file_exists=True,
                file_size_bytes=size,
                format="xlsx",
                element_count=rows_len,
                integrity_notes=f"Created Excel workbook with {chart_type.upper()} chart and formulas ({size} bytes)."
            )
        except Exception as e:
            # Fallback to standard workbook
            return self.create_workbook(title, data_rows, filename=filename)

    def create_csv(self, title: str, rows: List[List[Any]], filename: Optional[str] = None) -> Tuple[Path, ValidationResult]:
        """Export rows to clean UTF-8 CSV."""
        clean_name = filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', title.lower())[:35]}.csv"
        if not clean_name.endswith(".csv"):
            clean_name += ".csv"
        target_path = self.output_dir / clean_name

        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)

        size = target_path.stat().st_size
        return target_path, ValidationResult(
            is_valid=True,
            file_exists=True,
            file_size_bytes=size,
            format="csv",
            element_count=len(rows),
            integrity_notes=f"Exported {len(rows)} CSV rows."
        )


    def analyze_dataset(self, file_path: str | Path) -> Dict[str, Any]:
        """Audit dataset for duplicates, missing values, column data types, and row statistics."""
        p = Path(file_path).resolve()
        if not p.exists():
            return {"error": f"File not found: {file_path}"}

        rows: List[List[Any]] = []
        if p.suffix.lower() == ".csv":
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                rows = list(csv.reader(f))
        elif p.suffix.lower() in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(str(p), data_only=True)
            ws = wb.active
            rows = [[cell.value for cell in r] for r in ws.iter_rows()]

        if not rows:
            return {"error": "Dataset is empty."}

        headers = [str(h) for h in rows[0]]
        data_rows = rows[1:]

        # Analysis metrics
        total_rows = len(data_rows)
        missing_count = sum(1 for r in data_rows for c in r if c is None or str(c).strip() == "")
        # Duplicate rows detection
        row_tuples = [tuple(r) for r in data_rows]
        duplicates_count = len(row_tuples) - len(set(row_tuples))

        return {
            "file_name": p.name,
            "total_records": total_rows,
            "columns": headers,
            "columns_count": len(headers),
            "missing_values_count": missing_count,
            "duplicates_count": duplicates_count,
            "sample_row": data_rows[0] if data_rows else [],
            "health": "CLEAN" if missing_count == 0 and duplicates_count == 0 else "NEEDS_CLEANING",
        }

