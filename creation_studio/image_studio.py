"""
creation_studio/image_studio.py — Multimodal Image Processing, Transparent Cutouts & Graphic Studio.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from creation_studio.models import OutputFormat, ValidationResult


class ImageStudio:
    """Non-destructive image manipulation studio:

    - Crop, resize, rotate
    - Background transparency / color-key cutout
    - Lighting & color enhancement (contrast, sharpness, brightness)
    - Format conversion (PNG, JPG, WEBP)
    - Graphic / text overlays & watermarks
    - Always preserves original image by writing to a new deliverable file
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_image(
        self,
        image_path: str | Path,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        output_filename: Optional[str] = None,
    ) -> Tuple[Path, ValidationResult]:
        """Perform non-destructive transformation on source image."""
        src = Path(image_path).resolve()
        if not src.exists():
            return src, ValidationResult(
                is_valid=False,
                file_exists=False,
                file_size_bytes=0,
                format="",
                error_message=f"Source image '{image_path}' not found."
            )

        p = params or {}
        op = operation.lower().strip()
        clean_name = output_filename or f"{src.stem}_{op}{src.suffix}"
        target_path = self.output_dir / clean_name

        try:
            from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

            img = Image.open(src)
            res = img.copy()

            if op == "resize":
                w = int(p.get("width", img.width // 2))
                h = int(p.get("height", img.height // 2))
                res = img.resize((w, h), Image.Resampling.LANCZOS)

            elif op == "crop":
                box = p.get("box", [0, 0, img.width // 2, img.height // 2])
                res = img.crop(tuple(box))

            elif op == "rotate":
                deg = float(p.get("degrees", 90))
                res = img.rotate(deg, expand=True)

            elif op == "enhance":
                contrast = float(p.get("contrast", 1.2))
                sharpness = float(p.get("sharpness", 1.3))
                brightness = float(p.get("brightness", 1.05))
                e = ImageEnhance.Contrast(res).enhance(contrast)
                e = ImageEnhance.Sharpness(e).enhance(sharpness)
                res = ImageEnhance.Brightness(e).enhance(brightness)

            elif op in ("remove_background", "transparent_cutout"):
                # Color-key / luminance alpha channel creation for transparent cutout
                res = res.convert("RGBA")
                datas = res.getdata()
                new_data = []
                # Remove pure white or near-white background
                threshold = int(p.get("threshold", 240))
                for item in datas:
                    if item[0] >= threshold and item[1] >= threshold and item[2] >= threshold:
                        new_data.append((255, 255, 255, 0))  # Transparent
                    else:
                        new_data.append(item)
                res.putdata(new_data)
                # Force PNG output for transparency
                if not target_path.suffix.lower() == ".png":
                    target_path = target_path.with_suffix(".png")

            elif op == "watermark":
                res = res.convert("RGBA")
                draw = ImageDraw.Draw(res)
                text = p.get("text", "ALEX • Aditya Sir")
                # Draw high-contrast text overlay
                pos = (20, res.height - 40)
                draw.text((pos[0] + 1, pos[1] + 1), text, fill=(0, 0, 0, 180))
                draw.text(pos, text, fill=(255, 255, 255, 230))

            elif op == "convert":
                fmt = p.get("format", "png").lower().lstrip(".")
                target_path = target_path.with_suffix(f".{fmt}")
                if fmt in ("jpg", "jpeg") and res.mode in ("RGBA", "P"):
                    res = res.convert("RGB")

            elif op == "thumbnail":
                size = tuple(p.get("size", (256, 256)))
                res.thumbnail(size)

            else:
                return target_path, ValidationResult(
                    is_valid=False,
                    file_exists=False,
                    file_size_bytes=0,
                    format=src.suffix,
                    error_message=f"Unknown image operation '{operation}'."
                )

            res.save(target_path)
            size = target_path.stat().st_size

            return target_path, ValidationResult(
                is_valid=True,
                file_exists=True,
                file_size_bytes=size,
                format=target_path.suffix.lstrip("."),
                element_count=res.width * res.height,
                integrity_notes=f"Operation '{op}' succeeded: {res.width}x{res.height} px ({size} bytes)."
            )

        except Exception as e:
            return target_path, ValidationResult(
                is_valid=False,
                file_exists=target_path.exists(),
                file_size_bytes=0,
                format=src.suffix,
                error_message=f"Image processing failed: {e}"
            )

