# ALEX 3D Digital Human Avatar Pipeline & Integration Guide

## 1. Overview
ALEX now features a personalized 3D digital human avatar modeled after **Aditya Rajak** (`aadi.png`), replacing the legacy 2D wireframe ring stack.

The avatar architecture provides:
- **Genuine 3D GLTF 2.0 Binary (`.glb`) character asset** with standard vertex geometry, vertex normals, texture coordinates, and PBR materials.
- **Morph targets / Blendshapes**:
  - `jawOpen`: Driven by real-time PCM audio amplitude and phoneme/viseme data for speech lip-sync.
  - `mouthSmile`: Friendly reaction for `SUCCESS` and greeting states.
  - `eyeBlinkLeft` & `eyeBlinkRight`: Automatic randomized natural blinking (~150ms duration, 2–5s intervals).
  - `browRaise`: Attentive facial expression during `LISTENING` and `THINKING`.
- **Dual-Engine Architecture**:
  1. **Embedded WebGL / Three.js Engine**: Hosted via local HTTP (`core/avatar_service.py` and `dashboard/server.py`), rendering PBR studio key/fill/rim lighting, soft shadows, camera orbit/damping, and particle systems.
  2. **Native 3D Viewport Widget (`Avatar3DViewport`)**: Ultra-responsive direct PyQt6 hardware-accelerated 3D viewport embedded in the Right Panel. Failures in external WebGL never affect or crash the assistant.

---

## 2. Avatar State Machine
The 3D avatar transitions smoothly between 8 distinct assistant states:

| State | Visual Behavior | Facial Expression & Accents |
|---|---|---|
| **IDLE** | Natural breathing, subtle micro-saccades, gentle head sway | Neutral, friendly, electric cyan accent ring |
| **LISTENING** | Attentive forward posture, active soundwave monitor | Raised brows, soft emerald cyan listening glow |
| **THINKING** | Orbiting particle ring, active cognitive pulse | Deep focus expression, electric violet glow |
| **SPEAKING** | High-fidelity mouth articulation synced to audio RMS & visemes | Synchronized jawOpen blendshape, vibrant cyan lighting |
| **EXECUTING** | Smooth activity indicator while automation tools run | Attentive posture, amber tool activity glow |
| **SUCCESS** | Brief positive affirmation and friendly smile | Warm `mouthSmile` blendshape, emerald green confirmation |
| **ERROR** | Calm diagnostic alert indicator without exaggerated distortion | Controlled posture, soft ruby warning glow |
| **SLEEPING** | Eyes closed, slow deep breathing, dimmed lighting | Inactive dimmed state (35% luminance), muted aura |

---

## 3. Asset Files & Pipeline

### Included Assets:
- `assets/avatar/aadi.png`: Original reference portrait of Aditya Rajak.
- `assets/avatar/alex_skin_texture.png`: 1024x1024 diffuse PBR texture atlas generated from `aadi.png` with navy blazer and cybernetic cyan accents.
- `assets/avatar/alex_avatar.glb`: Pre-built, verified 3D GLB digital human model.
- `dashboard/static/avatar/`: WebGL Three.js web application with `index.html`, `alex_avatar.glb`, and Three.js modules (`three.module.js`, `GLTFLoader.js`, `OrbitControls.js`).

### Generating or Customizing the Model:
To regenerate or modify the model:
```powershell
python core/avatar_model_builder.py
```
This reads `aadi.png` and canonical facial anatomy (`core/avatar_mesh.py`), compiles the blendshapes (`jawOpen`, `mouthSmile`, `eyeBlinkLeft`, `eyeBlinkRight`, `browRaise`), generates the tailored dark navy suit with cyan lapel accents, and compiles the binary `.glb`.

### Importing External 3D Models (ReadyPlayerMe, Meshy, Rodin, Blender):
You can drop any standard rigged GLB/GLTF model into ALEX:
1. Export your character from ReadyPlayerMe, Avaturn, Meshy, or Blender as a `.glb` file.
2. Ensure standard ARKit/Oculus visemes or blendshapes are present:
   - `jawOpen` (or `mouthOpen`)
   - `mouthSmile`
   - `eyeBlinkLeft` / `eyeBlinkRight`
3. Place the `.glb` file at `assets/avatar/alex_avatar.glb` and `dashboard/static/avatar/alex_avatar.glb`.
4. Restart ALEX. The Three.js WebGL engine and avatar bridge automatically bind to matching morph targets.

---

## 4. Launching & Testing

### Running the ALEX Desktop Assistant:
```powershell
python main.py
```

### Previewing the 3D Avatar WebGL Scene Standalone:
To preview the Three.js 3D avatar independently:
```powershell
python -c "from core.avatar_service import avatar_server; import time, webbrowser; port = avatar_server.start_server(); webbrowser.open(f'http://127.0.0.1:{port}/index.html'); time.sleep(60)"
```

### Running Automated Test Suite:
```powershell
python test_desktop_app_integration.py
```

