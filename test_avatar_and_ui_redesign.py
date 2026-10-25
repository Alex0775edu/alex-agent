"""
test_avatar_and_ui_redesign.py — Comprehensive Test Suite for ALEX UI Redesign
and 3D Avatar Integration (Aditya Rajak Edition).
"""

import json
import os
import struct
import sys
import unittest
import urllib.request
from pathlib import Path

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Initialize Qt App once for the test process
app = QApplication.instance() or QApplication(sys.argv)

from core.avatar_bridge import AvatarBridge, avatar_bridge
from core.avatar_service import avatar_server
from core.avatar_widget import Avatar3DViewport, AvatarContainerWidget
from ui import AlexUI, MainWindow


class Test3DAvatarAssetAndPipeline(unittest.TestCase):
    """Validates the 3D Avatar GLB asset, textures, and pipeline."""

    def test_portrait_reference_exists(self):
        """Verify the reference portrait of Aditya Rajak exists in project."""
        p1 = BASE_DIR / "aadi.png"
        p2 = BASE_DIR / "assets" / "avatar" / "aadi.png"
        self.assertTrue(p1.exists() or p2.exists(), "Reference portrait aadi.png must exist.")

    def test_texture_atlas_exists(self):
        """Verify the generated PBR skin texture atlas exists."""
        tex1 = BASE_DIR / "assets" / "avatar" / "alex_skin_texture.png"
        tex2 = BASE_DIR / "dashboard" / "static" / "avatar" / "alex_skin_texture.png"
        self.assertTrue(tex1.exists(), "assets/avatar/alex_skin_texture.png must exist.")
        self.assertTrue(tex2.exists(), "dashboard/static/avatar/alex_skin_texture.png must exist.")

    def test_glb_model_binary_structure(self):
        """Verify alex_avatar.glb is a valid GLTF 2.0 binary file with morph targets."""
        glb_path = BASE_DIR / "assets" / "avatar" / "alex_avatar.glb"
        self.assertTrue(glb_path.exists(), "alex_avatar.glb must exist.")
        self.assertGreater(glb_path.stat().st_size, 50000, "GLB model must be substantive 3D geometry.")

        with open(glb_path, "rb") as f:
            magic, version, total_len = struct.unpack("<4sII", f.read(12))
            self.assertEqual(magic, b"glTF", "GLB header magic must be b'glTF'")
            self.assertEqual(version, 2, "GLTF version must be 2")
            self.assertEqual(total_len, glb_path.stat().st_size)

            # Read chunk 0 (JSON)
            c0_len, c0_type = struct.unpack("<II", f.read(8))
            self.assertEqual(c0_type, 0x4E4F534A, "Chunk 0 must be JSON")
            json_bytes = f.read(c0_len)
            data = json.loads(json_bytes.decode("utf-8"))

            # Verify morph targets
            mesh = data["meshes"][0]
            target_names = mesh.get("extras", {}).get("targetNames", [])
            for target in ["jawOpen", "mouthSmile", "eyeBlinkLeft", "eyeBlinkRight", "browRaise"]:
                self.assertIn(target, target_names, f"Target '{target}' missing from GLB morph targets.")


class Test3DAvatarWebGLService(unittest.TestCase):
    """Validates the local Three.js WebGL server and assets."""

    def test_static_threejs_libraries(self):
        """Verify Three.js and loaders are bundled locally."""
        libs_dir = BASE_DIR / "dashboard" / "static" / "avatar" / "libs"
        self.assertTrue((libs_dir / "three.module.js").exists(), "three.module.js must be present.")
        self.assertTrue((libs_dir / "GLTFLoader.js").exists(), "GLTFLoader.js must be present.")
        self.assertTrue((libs_dir / "OrbitControls.js").exists(), "OrbitControls.js must be present.")

    def test_avatar_html_exists(self):
        """Verify the avatar Three.js HTML entry point exists."""
        html_p = BASE_DIR / "dashboard" / "static" / "avatar" / "index.html"
        self.assertTrue(html_p.exists(), "avatar index.html must exist.")
        content = html_p.read_text(encoding="utf-8")
        self.assertIn("Three.js", content)
        self.assertIn("alex_avatar.glb", content)

    def test_avatar_http_serving(self):
        """Verify the background HTTP service serves the 3D avatar application."""
        port = avatar_server.start_server()
        self.assertGreater(port, 1024)
        
        # Test index.html HTTP 200
        url = f"http://127.0.0.1:{port}/index.html"
        req = urllib.request.urlopen(url, timeout=3)
        self.assertEqual(req.status, 200)
        self.assertGreater(len(req.read()), 1000)

        # Test GLB HTTP 200
        glb_url = f"http://127.0.0.1:{port}/alex_avatar.glb"
        g_req = urllib.request.urlopen(glb_url, timeout=3)
        self.assertEqual(g_req.status, 200)
        self.assertGreater(len(g_req.read()), 50000)


class TestAvatarBridgeAndEvents(unittest.TestCase):
    """Validates the avatar bridge state dispatch and event taxonomy."""

    def test_all_8_avatar_states(self):
        """Test transitions across all 8 required avatar states."""
        avatar_bridge.state = "INIT"
        states = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "EXECUTING", "SUCCESS", "ERROR", "SLEEPING"]
        received_states = []

        def listener(ev):
            if ev.get("type") == "state":
                received_states.append(ev.get("state"))

        avatar_bridge.add_listener(listener)
        for st in states:
            avatar_bridge.set_state(st)
            self.assertEqual(avatar_bridge.state, st)

        avatar_bridge.remove_listener(listener)
        for st in states:
            self.assertIn(st, received_states)

    def test_audio_level_dispatch(self):
        """Test audio level normalization and dispatch."""
        received_levels = []

        def listener(ev):
            if ev.get("type") == "audio_level":
                received_levels.append(ev.get("level"))

        avatar_bridge.add_listener(listener)
        avatar_bridge.set_audio_level(0.72)
        avatar_bridge.remove_listener(listener)

        self.assertAlmostEqual(avatar_bridge.audio_level, 0.72, places=2)
        self.assertIn(0.72, received_levels)


class TestDesktopUIRedesign(unittest.TestCase):
    """Validates the redesigned desktop UI components and layout."""

    @classmethod
    def setUpClass(cls):
        cls.ui = AlexUI("face.png")
        cls.win = cls.ui._win

    def test_window_geometry(self):
        """Verify window default dimensions matching redesigned layout."""
        self.assertGreaterEqual(self.win.width(), 940)
        self.assertGreaterEqual(self.win.height(), 600)

    def test_left_sidebar_and_10_navigation_buttons(self):
        """Verify Left Sidebar presence and all 10 navigation buttons."""
        self.assertTrue(hasattr(self.win, "_left_panel"))
        self.assertTrue(hasattr(self.win, "_nav_buttons"))

        required_keys = [
            "home", "voice", "tasks", "projects", "files",
            "tools", "browser", "coding", "memory", "settings"
        ]
        for key in required_keys:
            self.assertIn(key, self.win._nav_buttons, f"Missing nav button: {key}")
            btn = self.win._nav_buttons[key]
            self.assertTrue(btn.isCheckable())

    def test_main_center_area_components(self):
        """Verify Center Area: Task Progress, Conversation Log, and Command Input."""
        # Task progress card
        self.assertTrue(hasattr(self.win, "_task_card"))
        self.assertTrue(hasattr(self.win, "_task_status_lbl"))
        self.assertTrue(hasattr(self.win, "_task_progress_bar"))

        # Conversation log
        self.assertTrue(hasattr(self.win, "_log"))

        # Center input bar controls
        self.assertTrue(hasattr(self.win, "_input_bar"))
        self.assertTrue(hasattr(self.win, "_input"))
        self.assertTrue(hasattr(self.win, "_mic_btn"))
        self.assertTrue(hasattr(self.win, "_send_btn"))
        self.assertTrue(hasattr(self.win, "_interrupt_btn"))

    def test_right_panel_and_3d_avatar_integration(self):
        """Verify Right Panel: 3D Avatar Viewport, System Health, and Drop Zone."""
        self.assertTrue(hasattr(self.win, "_right_panel"))
        self.assertTrue(hasattr(self.win, "avatar_container"))
        self.assertIsInstance(self.win.avatar_container, AvatarContainerWidget)

        # 3D Viewport
        viewport = self.win.avatar_container.viewport
        self.assertIsInstance(viewport, Avatar3DViewport)

        # System metric bars
        self.assertTrue(hasattr(self.win, "_bar_cpu"))
        self.assertTrue(hasattr(self.win, "_bar_mem"))
        self.assertTrue(hasattr(self.win, "_bar_gpu"))
        self.assertTrue(hasattr(self.win, "_bar_net"))
        self.assertTrue(hasattr(self.win, "_bar_tmp"))

        # File Drop Zone
        self.assertTrue(hasattr(self.win, "_drop_zone"))

    def test_header_components(self):
        """Verify Header: Branding, Online Status, and Control Buttons."""
        self.assertTrue(hasattr(self.win, "_hdr_status_lbl"))
        self.assertTrue(hasattr(self.win, "_drawer_btn"))
        self.assertTrue(hasattr(self.win, "_ctrl_btn"))
        self.assertTrue(hasattr(self.win, "_lock_btn"))
        self.assertTrue(hasattr(self.win, "_emergency_btn"))
        self.assertTrue(hasattr(self.win, "_clock_lbl"))

    def test_ui_state_propagation(self):
        """Verify state change on AlexUI updates avatar viewport and status header."""
        self.ui.set_state("THINKING")
        self.assertEqual(self.win.avatar_container.viewport.state, "THINKING")
        self.assertIn("THINKING", self.win._hdr_status_lbl.text())

        self.ui.set_state("EXECUTING")
        self.assertEqual(self.win.avatar_container.viewport.state, "EXECUTING")
        self.assertIn("EXECUTING", self.win._hdr_status_lbl.text())

        self.ui.set_state("SUCCESS")
        self.assertEqual(self.win.avatar_container.viewport.state, "SUCCESS")
        self.assertIn("SUCCESS", self.win._hdr_status_lbl.text())

        self.ui.set_state("IDLE")
        self.assertEqual(self.win.avatar_container.viewport.state, "IDLE")

    def test_ui_audio_level_propagation(self):
        """Verify audio level updates the 3D avatar viewport."""
        self.ui.set_audio_level(0.65)
        self.assertAlmostEqual(self.win.avatar_container.viewport.target_audio_level, 0.65, places=2)


class TestDuplicateAvatarElimination(unittest.TestCase):
    """Verifies that the old wireframe HoloAvatar is retired and only ONE avatar exists."""

    @classmethod
    def setUpClass(cls):
        cls.ui = AlexUI("face.png")
        cls.win = cls.ui._win

    def test_hud_canvas_does_not_render_holo_avatar(self):
        """Verify HudCanvas in center panel has retired HoloAvatar and is set to core visualizer."""
        self.assertIsNone(self.win.hud._avatar, "Old wireframe HoloAvatar must be retired from HudCanvas.")
        self.assertEqual(self.win.hud.hud_style, "core", "HudCanvas must be in Quantum Core visualizer mode.")

    def test_single_active_avatar_widget(self):
        """Verify exactly ONE active avatar container exists on MainWindow."""
        self.assertTrue(hasattr(self.win, "avatar_container"))
        self.assertIsInstance(self.win.avatar_container, AvatarContainerWidget)

    def test_validation_renders_exist(self):
        """Verify photographic validation renders from Blender exist."""
        f_render = BASE_DIR / "memory" / "artifacts" / "avatar_renders" / "alex_avatar_front.png"
        t_render = BASE_DIR / "memory" / "artifacts" / "avatar_renders" / "alex_avatar_three_quarter.png"
        self.assertTrue(f_render.exists(), "Front-facing validation render must exist.")
        self.assertTrue(t_render.exists(), "Three-quarter validation render must exist.")
        self.assertGreater(f_render.stat().st_size, 100000)
        self.assertGreater(t_render.stat().st_size, 100000)

    def test_desktop_ui_screenshots_captured(self):
        """Verify UI screenshots of the running desktop application exist."""
        s1 = BASE_DIR / "memory" / "artifacts" / "avatar_renders" / "alex_desktop_ui_screenshot.png"
        s2 = BASE_DIR / "memory" / "artifacts" / "avatar_renders" / "alex_desktop_speaking_screenshot.png"
        self.assertTrue(s1.exists(), "Desktop UI screenshot must exist.")
        self.assertTrue(s2.exists(), "Desktop UI speaking screenshot must exist.")


if __name__ == "__main__":
    unittest.main()
