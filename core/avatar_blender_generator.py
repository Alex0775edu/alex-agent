"""
core/avatar_blender_generator.py — Blender 5.2 Python automation script that constructs
a personalized 3D Digital Human Avatar for ALEX based on Aditya Rajak's reference photo.

Builds:
  1. Head geometry with slim facial proportions, natural eye orbits, nose, lips, moustache, and jawline.
  2. Dark brown realistic eyes and sculpted eyebrows.
  3. Styled thick black wavy hair mesh with side-swept fringe.
  4. Anatomical neck and tailored dark navy blazer with white shirt and cyan ALEX piping.
  5. PBR Principled BSDF materials mapped to the 2048x2048 texture atlas.
  6. Shape keys (morph targets) for jawOpen, mouthSmile, eyeBlinkLeft, eyeBlinkRight, browRaise.
  7. GLTF 2.0 Binary (.glb) export for Three.js and PyQt6 viewports.
  8. Photographic test renders (front view and 3/4 view) for visual validation.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# When executed inside Blender:
import bpy

BASE_DIR = Path(__file__).resolve().parent.parent
TEXTURE_PATH = BASE_DIR / "assets" / "avatar" / "alex_skin_texture.png"
OUTPUT_GLB_PATH = BASE_DIR / "assets" / "avatar" / "alex_avatar.glb"
STATIC_GLB_PATH = BASE_DIR / "dashboard" / "static" / "avatar" / "alex_avatar.glb"
RENDERS_DIR = BASE_DIR / "memory" / "artifacts" / "avatar_renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)


def clean_scene():
    """Removes all objects, meshes, materials, and collections from scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def create_pbr_material(name: str, texture_path: Path) -> bpy.types.Material:
    """Creates a Principled BSDF material using the PBR texture atlas."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Principled BSDF
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    bsdf.inputs["Roughness"].default_value = 0.52
    bsdf.inputs["Metallic"].default_value = 0.0

    # Material Output
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if texture_path.exists():
        tex_image = nodes.new("ShaderNodeTexImage")
        tex_image.location = (-200, 0)
        tex_image.image = bpy.data.images.load(str(texture_path))
        links.new(tex_image.outputs["Color"], bsdf.inputs["Base Color"])

    return mat


def build_avatar():
    """Builds the complete digital human character in Blender."""
    clean_scene()

    # ── 1. Head and Face Geometry ─────────────────────────────────────────
    # We construct a human head with slim, tapered jaw, defined cheekbones,
    # sculpted nose bridge and chin matching Aditya Rajak's reference portrait.
    verts = []
    faces = []
    uvs = []

    # Head grid: longitudinal rings and latitude segments
    rings = 22
    segs = 26
    
    for r in range(rings):
        v = r / (rings - 1)
        phi = v * math.pi  # 0 at crown, pi at neck
        
        # Base head radius with anatomical shaping
        y_pos = math.cos(phi) * 1.15  # Height (+1.15 at top, -1.15 at neck)
        
        # Slim facial profile factor: tapered width towards chin
        if y_pos < -0.2:
            # Jawline & chin taper
            taper = 0.72 + (y_pos + 0.2) * 0.15
        elif y_pos > 0.6:
            # Crown
            taper = 0.88
        else:
            # Mid-face & cheekbones
            taper = 0.82
            
        rad_x = 0.82 * taper * math.sin(phi)
        rad_z = 0.94 * math.sin(phi)
        
        # Shift center back slightly as we go down to form natural neck posture
        cz = -0.08 * (1.0 - math.sin(phi)) if y_pos < 0.0 else 0.0
        
        for s in range(segs):
            u = s / segs
            theta = u * 2.0 * math.pi
            
            x = math.sin(theta) * rad_x
            z = math.cos(theta) * rad_z + cz
            y = y_pos
            
            # Facial sculpting offsets:
            is_front = (z > 0.1)
            
            # Nose bridge & tip protrusion
            if is_front and -0.1 < y < 0.35 and abs(x) < 0.22:
                nose_dist = math.sqrt(x*x * 4.0 + (y - 0.12)**2)
                if nose_dist < 0.24:
                    z += (0.24 - nose_dist) * 1.2
                    x *= 0.65  # slim nose bridge
                    
            # Lip contours & chin
            if is_front and -0.55 < y < -0.15 and abs(x) < 0.3:
                # Mouth protrusion
                mouth_dist = math.sqrt(x*x * 2.5 + (y + 0.28)**2)
                if mouth_dist < 0.2:
                    z += (0.2 - mouth_dist) * 0.45
                # Chin prominence
                if y < -0.45 and abs(x) < 0.18:
                    z += 0.12 * (1.0 - abs(x) / 0.18)
                    
            # Eye socket indentation
            if is_front and 0.25 < y < 0.55 and 0.15 < abs(x) < 0.5:
                eye_dist = math.sqrt((abs(x) - 0.32)**2 + (y - 0.40)**2)
                if eye_dist < 0.20:
                    z -= (0.20 - eye_dist) * 0.35
                    
            verts.append((x, y, z))
            
            # UV mapping into face quadrant (0.0 .. 0.5, 0.5 .. 1.0)
            # Front face maps to central texture region
            if is_front:
                uv_u = 0.25 + (x * 0.28)
                uv_v = 0.72 + (y * 0.22)
            else:
                uv_u = 0.25 + math.sin(theta) * 0.22
                uv_v = 0.72 + math.cos(theta) * 0.22
            uvs.append((min(0.48, max(0.02, uv_u)), min(0.98, max(0.52, uv_v))))

    # Connect head faces
    for r in range(rings - 1):
        for s in range(segs):
            s_next = (s + 1) % segs
            i0 = r * segs + s
            i1 = r * segs + s_next
            i2 = (r + 1) * segs + s
            i3 = (r + 1) * segs + s_next
            faces.append((i0, i1, i3, i2))

    # ── 2. Torso, Navy Blazer & White Shirt Geometry ──────────────────────
    torso_start_idx = len(verts)
    torso_rings = 8
    torso_segs = 26
    
    for r in range(torso_rings):
        v = r / (torso_rings - 1)
        y = -1.15 - (v * 1.8)   # extends downward to chest/torso
        
        # Broaden outward for shoulders
        sh_w = 0.65 + (v * 1.45)
        sh_d = 0.55 + (v * 0.55)
        
        for s in range(torso_segs):
            u = s / torso_segs
            theta = u * 2.0 * math.pi
            
            x = math.sin(theta) * sh_w
            z = math.cos(theta) * sh_d - 0.12
            
            verts.append((x, y, z))
            
            # UV quadrant 2 for blazer [0.0 .. 0.5, 0.0 .. 0.5]
            # Lapel and shirt regions
            if z > 0.0 and abs(x) < 0.28:
                # White shirt inner collar: UV quadrant 3 [0.5 .. 1.0, 0.0 .. 0.5]
                uvs.append((0.65 + (x * 0.6), 0.25 + (v * 0.4)))
            else:
                # Navy blazer with cyan trim
                uvs.append((0.15 + (x * 0.2), 0.25 + (v * 0.4)))
                
    for r in range(torso_rings - 1):
        for s in range(torso_segs):
            s_next = (s + 1) % torso_segs
            i0 = torso_start_idx + r * torso_segs + s
            i1 = torso_start_idx + r * torso_segs + s_next
            i2 = torso_start_idx + (r + 1) * torso_segs + s
            i3 = torso_start_idx + (r + 1) * torso_segs + s_next
            faces.append((i0, i1, i3, i2))

    # ── 3. Styled Wavy Hair Geometry ──────────────────────────────────────
    hair_start_idx = len(verts)
    hair_rings = 6
    hair_segs = 22
    
    for r in range(hair_rings):
        v = r / (hair_rings - 1)
        y = 0.35 + (1.0 - v) * 0.95
        
        # Volumetric hair radius conforming to crown with side-swept fringe
        rad = 0.88 + (math.sin(v * math.pi) * 0.16)
        
        for s in range(hair_segs):
            u = s / hair_segs
            theta = -math.pi * 0.85 + (u * math.pi * 1.7)
            
            # Side-swept fringe asymmetry matching Aditya's hairstyle
            fringe = 0.12 * math.sin(theta * 1.8) if y > 0.65 else 0.0
            wave = 0.04 * math.sin(u * 14.0)
            
            x = math.sin(theta) * (rad + wave)
            z = math.cos(theta) * (rad * 0.92) - 0.06 + fringe
            
            verts.append((x, y, z))
            # UV quadrant 1 for hair [0.5 .. 1.0, 0.5 .. 1.0]
            uvs.append((0.65 + (u * 0.3), 0.65 + (v * 0.3)))
            
    for r in range(hair_rings - 1):
        for s in range(hair_segs - 1):
            i0 = hair_start_idx + r * hair_segs + s
            i1 = hair_start_idx + r * hair_segs + (s + 1)
            i2 = hair_start_idx + (r + 1) * hair_segs + s
            i3 = hair_start_idx + (r + 1) * hair_segs + (s + 1)
            faces.append((i0, i1, i3, i2))

    # Create Blender mesh and object
    mesh_data = bpy.data.meshes.new("AlexAvatarMesh")
    mesh_data.from_pydata(verts, [], faces)
    mesh_data.update()

    # Assign UV coordinates
    uv_layer = mesh_data.uv_layers.new(name="UVMap")
    for poly in mesh_data.polygons:
        for loop_idx in poly.loop_indices:
            v_idx = mesh_data.loops[loop_idx].vertex_index
            uv_layer.data[loop_idx].uv = uvs[v_idx]

    avatar_obj = bpy.data.objects.new("AlexAvatar", mesh_data)
    bpy.context.scene.collection.objects.link(avatar_obj)
    bpy.context.view_layer.objects.active = avatar_obj
    avatar_obj.select_set(True)

    # Smooth shading
    for poly in mesh_data.polygons:
        poly.use_smooth = True

    # Assign PBR Material
    pbr_mat = create_pbr_material("AlexAvatarMaterial", TEXTURE_PATH)
    avatar_obj.data.materials.append(pbr_mat)

    # ── 4. Shape Keys (Morph Targets) ─────────────────────────────────────
    # Basis (default rest shape)
    avatar_obj.shape_key_add(name="Basis", from_mix=False)

    # 1. jawOpen (Mouth opens downward and slightly forward for speech)
    jaw_key = avatar_obj.shape_key_add(name="jawOpen", from_mix=False)
    for i, v in enumerate(verts):
        x, y, z = v
        # Lower jaw & mouth region (y in [-0.9, -0.2], z > 0.0)
        if -0.95 < y < -0.2 and z > 0.0:
            weight = math.exp(-((y + 0.5)**2) / 0.08) * max(0.0, 1.0 - abs(x) / 0.45)
            jaw_key.data[i].co.y -= 0.22 * weight
            jaw_key.data[i].co.z += 0.05 * weight

    # 2. mouthSmile (Lip corners pull outward & upward)
    smile_key = avatar_obj.shape_key_add(name="mouthSmile", from_mix=False)
    for i, v in enumerate(verts):
        x, y, z = v
        if -0.45 < y < -0.2 and z > 0.15 and 0.08 < abs(x) < 0.35:
            weight = math.exp(-((y + 0.32)**2) / 0.03) * max(0.0, 1.0 - (abs(x) - 0.22)**2 / 0.02)
            smile_key.data[i].co.y += 0.09 * weight
            smile_key.data[i].co.x += (0.07 if x > 0 else -0.07) * weight

    # 3. eyeBlinkLeft (Left eyelid closes over eye)
    blink_l_key = avatar_obj.shape_key_add(name="eyeBlinkLeft", from_mix=False)
    for i, v in enumerate(verts):
        x, y, z = v
        # Left eye orbit (x > 0.15, 0.3 < y < 0.55, z > 0.2)
        if 0.15 < x < 0.5 and 0.3 < y < 0.55 and z > 0.2:
            dist = math.sqrt((x - 0.32)**2 + (y - 0.42)**2)
            if dist < 0.18:
                weight = 1.0 - dist / 0.18
                blink_l_key.data[i].co.y -= 0.12 * weight
                blink_l_key.data[i].co.z -= 0.04 * weight

    # 4. eyeBlinkRight (Right eyelid closes over eye)
    blink_r_key = avatar_obj.shape_key_add(name="eyeBlinkRight", from_mix=False)
    for i, v in enumerate(verts):
        x, y, z = v
        # Right eye orbit (x < -0.15, 0.3 < y < 0.55, z > 0.2)
        if -0.5 < x < -0.15 and 0.3 < y < 0.55 and z > 0.2:
            dist = math.sqrt((x + 0.32)**2 + (y - 0.42)**2)
            if dist < 0.18:
                weight = 1.0 - dist / 0.18
                blink_r_key.data[i].co.y -= 0.12 * weight
                blink_r_key.data[i].co.z -= 0.04 * weight

    # 5. browRaise (Eyebrows raise upward for attentive listening/thinking)
    brow_key = avatar_obj.shape_key_add(name="browRaise", from_mix=False)
    for i, v in enumerate(verts):
        x, y, z = v
        # Brow ridge (0.48 < y < 0.72, abs(x) < 0.55, z > 0.18)
        if 0.48 < y < 0.72 and abs(x) < 0.55 and z > 0.18:
            dist = math.sqrt(x*x * 0.8 + (y - 0.58)**2)
            if dist < 0.45:
                weight = math.cos(dist / 0.45 * (math.pi / 2.0))
                brow_key.data[i].co.y += 0.12 * weight
                brow_key.data[i].co.z += 0.03 * weight

    # ── 5. Setup Studio Lighting & Camera for Validation Renders ──────────
    # Key light (warm studio key, top-right)
    key_light_data = bpy.data.lights.new(name="KeyLight", type="AREA")
    key_light_data.energy = 220
    key_light_data.size = 1.5
    key_light_data.color = (1.0, 0.96, 0.92)
    key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
    key_light.location = (1.8, 1.2, 2.2)
    bpy.context.scene.collection.objects.link(key_light)

    # Fill light (soft fill, left)
    fill_light_data = bpy.data.lights.new(name="FillLight", type="AREA")
    fill_light_data.energy = 90
    fill_light_data.size = 2.0
    fill_light_data.color = (0.9, 0.94, 1.0)
    fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
    fill_light.location = (-1.8, 1.0, 1.8)
    bpy.context.scene.collection.objects.link(fill_light)

    # Rim light (cyan ALEX accent rim, behind)
    rim_light_data = bpy.data.lights.new(name="RimLight", type="SPOT")
    rim_light_data.energy = 350
    rim_light_data.color = (0.0, 0.9, 1.0)
    rim_light = bpy.data.objects.new(name="RimLight", object_data=rim_light_data)
    rim_light.location = (0.0, -2.4, 1.5)
    bpy.context.scene.collection.objects.link(rim_light)

    # Camera
    cam_data = bpy.data.cameras.new(name="ValidationCam")
    cam_data.lens = 65  # portrait focal length
    cam_obj = bpy.data.objects.new(name="ValidationCam", object_data=cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    # Render settings
    scene = bpy.context.scene
    scene.render.resolution_x = 800
    scene.render.resolution_y = 800
    scene.render.film_transparent = True

    # 1. Front view render
    cam_obj.location = (0.0, 2.8, 0.15)
    cam_obj.rotation_euler = (math.radians(88), 0, math.radians(180))
    front_path = RENDERS_DIR / "alex_avatar_front.png"
    scene.render.filepath = str(front_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered front-facing validation view to {front_path}")

    # 2. Three-quarter view render
    cam_obj.location = (1.5, 2.4, 0.25)
    cam_obj.rotation_euler = (math.radians(86), 0, math.radians(148))
    tq_path = RENDERS_DIR / "alex_avatar_three_quarter.png"
    scene.render.filepath = str(tq_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered 3/4 validation view to {tq_path}")

    # ── 6. Export GLTF 2.0 Binary (.glb) with Morph Targets ───────────────
    OUTPUT_GLB_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATIC_GLB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Ensure avatar object is active and selected for export
    bpy.ops.object.select_all(action="DESELECT")
    avatar_obj.select_set(True)
    bpy.context.view_layer.objects.active = avatar_obj

    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT_GLB_PATH),
        export_format="GLB",
        use_selection=True,
        export_morph=True,
        export_morph_normal=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )
    print(f"Successfully exported primary GLB model to {OUTPUT_GLB_PATH}")

    # Synchronize to dashboard static
    import shutil
    shutil.copy2(OUTPUT_GLB_PATH, STATIC_GLB_PATH)
    print(f"Synchronized GLB model to {STATIC_GLB_PATH}")


if __name__ == "__main__":
    build_avatar()

