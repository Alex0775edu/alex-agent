"""
core/avatar_texture_builder.py — Generates a high-resolution 2048x2048 PBR texture atlas
derived directly from the reference portrait of Aditya Rajak (aditya_reference.png).
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

BASE_DIR = Path(__file__).resolve().parent.parent
REF_IMAGE_PATH = BASE_DIR / "assets" / "avatar" / "reference" / "aditya_reference.png"
OUTPUT_TEXTURE_PATH = BASE_DIR / "assets" / "avatar" / "alex_skin_texture.png"
STATIC_TEXTURE_PATH = BASE_DIR / "dashboard" / "static" / "avatar" / "alex_skin_texture.png"


def build_pbr_texture_atlas(output_path: Path = OUTPUT_TEXTURE_PATH) -> Path:
    """
    Synthesizes a 2048x2048 PBR diffuse texture atlas containing:
      - Face UV region: High-resolution seamless frontal portrait of Aditya Rajak,
        with green-screen background cleanly eliminated and skin tones blended.
      - Hair UV region: Thick black styled hair with natural specular variance.
      - Blazer UV region: Tailored dark navy wool texture (#1c2338) with cyan piping (#00e5ff).
      - Shirt UV region: Crisp white collared shirt with subtle shading.
    """
    tex_w, tex_h = 2048, 2048
    atlas = Image.new("RGBA", (tex_w, tex_h), (28, 32, 44, 255))

    # 1. Base skin fill for head (warm natural medium-brown: #cf9c8a)
    skin_base = Image.new("RGBA", (1024, 1024), (207, 156, 138, 255))
    atlas.paste(skin_base, (0, 0))

    if REF_IMAGE_PATH.exists():
        ref_img = Image.open(REF_IMAGE_PATH).convert("RGBA")
        rw, rh = ref_img.size

        # Exact, anatomically verified head crop:
        # X: 165 to 635 (spans both cheeks, ears, jawline, chin)
        # Y: 205 to 435 (spans hair crown, forehead, eyes, nose, moustache, lips, chin)
        fx0, fy0, fx1, fy1 = 165, 205, 635, 435
        face_crop = ref_img.crop((fx0, fy0, fx1, fy1))

        # Chroma-key remove green background cleanly
        arr = np.array(face_crop)
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        green_mask = (g > 135) & (g > r * 1.08) & (g > b * 1.08)
        arr[green_mask, 3] = 0

        # Create cleaned face image and resize to UV head area
        cleaned_face = Image.fromarray(arr, "RGBA")
        cleaned_face = cleaned_face.resize((860, 860), Image.Resampling.LANCZOS)

        # Create smooth feathered boundary mask for natural spherical blending
        mask = Image.new("L", (860, 860), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.ellipse([40, 30, 820, 830], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=32))

        # Paste face into UV quadrant 0 (0..1024, 0..1024)
        atlas.paste(cleaned_face, (82, 82), mask)

        # 3. White Collared Shirt Region [1024..2048, 1024..2048]
        # Crop real collar and shirt texture directly from reference portrait
        shirt_crop = ref_img.crop((230, 415, 570, 550)).resize((1024, 1024), Image.Resampling.LANCZOS)
        atlas.paste(shirt_crop, (1024, 1024))

        # 4. Navy Blazer Fabric Region [0..1024, 1024..2048]
        # Extract authentic blazer wool texture
        blazer_crop = ref_img.crop((100, 530, 700, 760)).resize((1024, 1024), Image.Resampling.LANCZOS)
        atlas.paste(blazer_crop, (0, 1024))
    else:
        print(f"[WARN] Reference photo not found at {REF_IMAGE_PATH}")

    # Add electric cyan ALEX accent piping along lapel seams on blazer
    b_draw = ImageDraw.Draw(atlas)
    for x in range(40, 58):
        b_draw.line([(x, 1024), (x, 2048)], fill=(0, 229, 255, 255), width=1)
    for x in range(58, 80):
        alpha = int(255 * (1.0 - (x - 58) / 22.0))
        b_draw.line([(x, 1024), (x, 2048)], fill=(0, 229, 255, alpha), width=1)

    # 2. Hair Texture Region [1024..2048, 0..1024]
    # Deep natural black with subtle espresso strands and directional texture
    hair_block = Image.new("RGBA", (1024, 1024), (22, 20, 24, 255))
    h_draw = ImageDraw.Draw(hair_block)
    # Add procedural natural hair texture streaks
    np.random.seed(42)
    for _ in range(450):
        y0 = int(np.random.uniform(0, 1024))
        y1 = y0 + int(np.random.uniform(10, 45))
        x0 = int(np.random.uniform(0, 1024))
        x1 = x0 + int(np.random.uniform(50, 220))
        col_v = int(np.random.uniform(18, 40))
        h_draw.line([(x0, y0), (x1, y1)], fill=(col_v, col_v - 2, col_v + 1, 255), width=2)
    atlas.paste(hair_block, (1024, 0))

    # Save to assets and dashboard static directories
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output_path, format="PNG", quality=95)
    print(f"Saved PBR texture atlas to {output_path} ({tex_w}x{tex_h})")

    if STATIC_TEXTURE_PATH != output_path:
        STATIC_TEXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(STATIC_TEXTURE_PATH, format="PNG", quality=95)
        print(f"Synchronized texture atlas to {STATIC_TEXTURE_PATH}")

    return output_path


if __name__ == "__main__":
    build_pbr_texture_atlas()
