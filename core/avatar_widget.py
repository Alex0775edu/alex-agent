"""
core/avatar_widget.py — Dedicated 3D Digital Human Viewport Widget for PyQt6.

Renders Aditya Rajak's personalized 3D avatar directly into the right panel
of ALEX, with real-time morph targets, PBR studio lighting, idle breathing,
synchronized lip-sync, and state reactive holographic effects.
Also manages embedding/launching the Three.js WebGL viewport.
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QPolygonF
)
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
)

from core.avatar_bridge import AVATAR_STATES, avatar_bridge
from core.avatar_mesh import get_head_mesh, LANDMARKS
from core.avatar_service import avatar_server

BASE_DIR = Path(__file__).resolve().parent.parent


class Avatar3DViewport(QWidget):
    """
    High-performance 3D Digital Human Viewport for ALEX desktop UI.
    Provides real-time 3D rendering with PBR studio lighting, blendshapes,
    and reactive holographic assistant status indications.
    """
    state_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(280, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        # Avatar State
        self.state: str = "IDLE"
        self.speaking: bool = False
        self.audio_level: float = 0.0
        self.target_audio_level: float = 0.0

        # Load Stylized 3D Character Asset
        self._portrait_path = BASE_DIR / "assets" / "avatar" / "alex_avatar_front.png"
        self._portrait_pixmap = None
        if self._portrait_path.exists():
            pm = QPixmap(str(self._portrait_path))
            if not pm.isNull():
                self._portrait_pixmap = pm

        # Load 3D geometry (for mathematical rigging and mesh fallback)
        self._mesh = get_head_mesh()
        self._base_verts = self._mesh["verts"].copy().astype(np.float32)   # [N, 3]
        self._base_norms = self._mesh["normals"].copy().astype(np.float32) # [N, 3]
        self._faces = self._mesh["faces"].copy()                          # [M, 3]
        self._jaw_weight = self._mesh["jaw"].copy().astype(np.float32)    # [N]
        self._num_verts = len(self._base_verts)

        # Morph targets
        self._jaw_open = 0.0
        self._target_jaw_open = 0.0
        self._smile = 0.0
        self._target_smile = 0.0
        self._blink = 0.0
        self._brow = 0.0
        self._target_brow = 0.0

        # Animation timing
        self._time = 0.0
        self._blink_timer = 0.0
        self._next_blink = 3.0
        self._is_blinking = False
        self._blink_progress = 0.0

        # Interactive 3D Orbit & Mouse tracking
        self._rot_x = 0.0
        self._rot_y = 0.0
        self._target_rot_x = 0.0
        self._target_rot_y = 0.0
        self._dragging = False
        self._last_mouse = QPoint()

        # Camera distance
        self._cam_dist = 4.4

        # Register with AvatarBridge
        avatar_bridge.add_listener(self._on_bridge_event)

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)

    def _on_bridge_event(self, event: dict) -> None:
        t = event.get("type")
        if t == "state":
            self.set_state(event.get("state", "IDLE"))
        elif t == "audio_level":
            self.target_audio_level = event.get("level", 0.0)

    def set_state(self, state: str) -> None:
        norm = state.strip().upper()
        if norm not in AVATAR_STATES:
            norm = "IDLE"
        self.state = norm
        self.speaking = (norm == "SPEAKING")

        # Update expression targets
        if norm == "LISTENING":
            self._target_smile = 0.15
            self._target_brow = 0.4
        elif norm == "THINKING":
            self._target_smile = 0.0
            self._target_brow = 0.6
        elif norm == "SPEAKING":
            self._target_smile = 0.2
            self._target_brow = 0.1
        elif norm == "EXECUTING":
            self._target_smile = 0.1
            self._target_brow = 0.3
        elif norm == "SUCCESS":
            self._target_smile = 0.95  # Friendly smile
            self._target_brow = 0.15
        elif norm == "ERROR":
            self._target_smile = 0.0
            self._target_brow = 0.1
        elif norm == "SLEEPING":
            self._target_smile = 0.0
            self._target_brow = 0.0
        else: # IDLE
            self._target_smile = 0.1
            self._target_brow = 0.0

        self.state_changed.emit(norm)

    def set_audio_level(self, level: float) -> None:
        self.target_audio_level = max(0.0, min(1.0, float(level)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_mouse = event.pos()

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.pos() - self._last_mouse
            self._last_mouse = event.pos()
            self._target_rot_y += delta.x() * 0.008
            self._target_rot_x += delta.y() * 0.008
            self._target_rot_x = max(-0.4, min(0.4, self._target_rot_x))
            self._target_rot_y = max(-0.6, min(0.6, self._target_rot_y))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def reset_view(self):
        self._target_rot_x = 0.0
        self._target_rot_y = 0.0

    def _step(self):
        dt = 0.016
        self._time += dt

        # Smooth audio level
        self.audio_level += (self.target_audio_level - self.audio_level) * 0.35

        # Smooth orbit rotation
        if not self._dragging:
            # Subtle natural micro-sway when idle
            if self.state != "SLEEPING":
                sway_y = math.sin(self._time * 0.7) * 0.04
                sway_x = math.sin(self._time * 0.9) * 0.025
            else:
                sway_y = 0.0
                sway_x = 0.08
            self._target_rot_y += (sway_y - self._target_rot_y) * 0.02
            self._target_rot_x += (sway_x - self._target_rot_x) * 0.02

        self._rot_x += (self._target_rot_x - self._rot_x) * 0.12
        self._rot_y += (self._target_rot_y - self._rot_y) * 0.12

        # Smooth expressions
        self._smile += (self._target_smile - self._smile) * 0.1
        self._brow += (self._target_brow - self._brow) * 0.1

        # Smooth mouth articulation for speech
        if self.speaking or self.audio_level > 0.04:
            target_jaw = min(1.0, self.audio_level * 1.8 + math.sin(self._time * 22.0) * 0.08)
        else:
            target_jaw = 0.0
        self._jaw_open += (target_jaw - self._jaw_open) * 0.4

        # Blinking
        self._blink_timer += dt
        if not self._is_blinking and self._blink_timer > self._next_blink:
            self._is_blinking = True
            self._blink_progress = 0.0
            self._blink_timer = 0.0
            self._next_blink = 2.0 + random.random() * 3.5

        if self.state == "SLEEPING":
            self._blink = 1.0
        elif self._is_blinking:
            self._blink_progress += dt * 6.5
            if self._blink_progress < 1.0:
                self._blink = math.sin(self._blink_progress * math.pi)
            else:
                self._is_blinking = False
                self._blink = 0.0
        else:
            self._blink = 0.0

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0

        # Background gradient (Deep Dark Space Navy)
        bg = QRadialGradient(cx, cy * 0.85, max(W, H) * 0.75)
        bg.setColorAt(0.0, QColor(8, 18, 38))
        bg.setColorAt(0.65, QColor(4, 9, 20))
        bg.setColorAt(1.0, QColor(2, 5, 12))
        p.fillRect(self.rect(), QBrush(bg))

        # ── Holographic Status Halo & Particles ──
        self._draw_ambient_fx(p, cx, cy, min(W, H) * 0.44)

        if self._portrait_pixmap is not None:
            # ── High-Fidelity Stylized 3D Digital Human Rendering ──
            p.save()

            # Breathing vertical displacement and micro-sway
            breath_y = math.sin(self._time * 1.8) * 3.5 if self.state != "SLEEPING" else 0.0
            shift_x = self._rot_y * 28.0
            shift_y = -self._rot_x * 20.0 + breath_y

            # Attentive tilt during LISTENING / THINKING
            tilt_angle = 0.0
            if self.state == "LISTENING":
                tilt_angle = 2.5 + math.sin(self._time * 2.0) * 0.8
            elif self.state == "THINKING":
                tilt_angle = -2.0 + math.sin(self._time * 1.5) * 1.0
            elif self.state != "SLEEPING":
                tilt_angle = self._rot_y * 8.0

            p.translate(cx + shift_x, cy + shift_y)
            p.rotate(tilt_angle)

            # Subtle breathing scale
            b_scale = 1.0 + math.sin(self._time * 1.8) * 0.012 if self.state != "SLEEPING" else 0.98
            target_h = int(H * 0.92 * b_scale)
            scaled_pm = self._portrait_pixmap.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)

            pw, ph = scaled_pm.width(), scaled_pm.height()
            draw_x = -pw / 2.0
            draw_y = -ph / 2.0 + 8.0

            # Draw base portrait
            if self.state == "SLEEPING":
                p.setOpacity(0.55)
            else:
                p.setOpacity(1.0)
            p.drawPixmap(int(draw_x), int(draw_y), scaled_pm)

            # Real-time Speech Articulation (Jaw Open)
            if self._jaw_open > 0.04 and self.state != "SLEEPING":
                mouth_cx = 0.0
                mouth_cy = draw_y + ph * 0.485
                mw = pw * 0.14
                mh = (ph * 0.05) * min(1.0, self._jaw_open * 1.4)

                # Dark interior of mouth
                p.setBrush(QBrush(QColor(42, 18, 22, 230)))
                p.setPen(QPen(QColor(165, 85, 75, 180), 1.0))
                p.drawEllipse(QRectF(mouth_cx - mw / 2.0, mouth_cy - mh / 2.0, mw, mh))

                # Lower lip edge displacement
                p.setPen(QPen(QColor(185, 115, 105, 200), 1.5))
                p.drawArc(QRectF(mouth_cx - mw * 0.45, mouth_cy + mh * 0.1, mw * 0.9, mh * 0.8), 0, -180 * 16)

            # Natural Eye Blinking Overlay
            if (self._blink > 0.06 or self.state == "SLEEPING") and self.state != "SPEAKING":
                blink_amt = 1.0 if self.state == "SLEEPING" else self._blink
                eye_cy = draw_y + ph * 0.388
                eye_spacing = pw * 0.115
                eye_w = pw * 0.10
                eye_h = ph * 0.035 * blink_amt

                p.setBrush(QBrush(QColor(204, 154, 136, int(240 * blink_amt))))
                p.setPen(QPen(QColor(42, 32, 35, int(220 * blink_amt)), 1.4))
                # Left eye lid
                p.drawEllipse(QRectF(-eye_spacing - eye_w / 2.0, eye_cy - eye_h / 2.0, eye_w, eye_h))
                # Right eye lid
                p.drawEllipse(QRectF(eye_spacing - eye_w / 2.0, eye_cy - eye_h / 2.0, eye_w, eye_h))

            # Friendly smile crease highlight on SUCCESS
            if self._smile > 0.3:
                smile_w = pw * 0.15
                smile_y = draw_y + ph * 0.49
                p.setPen(QPen(QColor(215, 130, 115, int(180 * self._smile)), 1.5))
                p.drawArc(QRectF(-smile_w / 2.0, smile_y - 4, smile_w, 10), 0, -180 * 16)

            p.restore()
        else:
            # ── Fallback 3D Polygon Shaded Mesh ──
            verts = self._base_verts.copy()
            norms = self._base_norms.copy()

            if self._jaw_open > 0.01:
                jw = self._jaw_weight * self._jaw_open
                verts[:, 1] -= jw * 0.22
                verts[:, 2] -= jw * 0.05

            if self._smile > 0.01:
                for idx in LANDMARKS.get("lip_out", []):
                    if idx < self._num_verts:
                        vx = verts[idx, 0]
                        corner_w = abs(vx) / 0.35
                        verts[idx, 1] += self._smile * 0.07 * corner_w

            if self._blink > 0.01:
                for idx in LANDMARKS.get("eye_l", []) + LANDMARKS.get("eye_r", []):
                    if idx < self._num_verts and verts[idx, 1] > 0.0:
                        verts[idx, 1] -= self._blink * 0.08

            rx, ry = self._rot_x, self._rot_y
            cos_y, sin_y = math.cos(ry), math.sin(ry)
            cos_x, sin_x = math.cos(rx), math.sin(rx)

            x = verts[:, 0] * cos_y + verts[:, 2] * sin_y
            z = -verts[:, 0] * sin_y + verts[:, 2] * cos_y
            y = verts[:, 1] * cos_x - z * sin_x
            z = verts[:, 1] * sin_x + z * cos_x

            scale = min(W, H) * 0.42
            w_cam = np.maximum(self._cam_dist - z, 0.4)
            k = (self._cam_dist / w_cam) * scale

            breath_y = math.sin(self._time * 1.8) * 4.0 if self.state != "SLEEPING" else 0.0
            head_cy = cy + breath_y

            xs = cx + x * k
            ys = head_cy - y * k

            l_key = np.array([0.5, 0.7, 0.5])
            l_key /= np.linalg.norm(l_key)
            l_fill = np.array([-0.6, 0.3, 0.4])
            l_fill /= np.linalg.norm(l_fill)
            l_rim = np.array([0.0, 0.6, -0.8])
            l_rim /= np.linalg.norm(l_rim)

            fa, fb, fc = self._faces[:, 0], self._faces[:, 1], self._faces[:, 2]
            v0 = np.column_stack([x[fa], y[fa], z[fa]])
            v1 = np.column_stack([x[fb], y[fb], z[fb]])
            v2 = np.column_stack([x[fc], y[fc], z[fc]])
            fn = np.cross(v1 - v0, v2 - v0)
            fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)

            visible = fn[:, 2] > 0.02
            if np.any(visible):
                vis_indices = np.flatnonzero(visible)
                z_depth = (z[fa[vis_indices]] + z[fb[vis_indices]] + z[fc[vis_indices]]) / 3.0
                sorted_order = vis_indices[np.argsort(z_depth)]
                dim = 0.4 if self.state == "SLEEPING" else 1.0

                for idx in sorted_order:
                    ia, ib, ic = fa[idx], fb[idx], fc[idx]
                    norm = fn[idx]
                    diff_key = max(0.0, float(np.dot(norm, l_key)))
                    diff_fill = max(0.0, float(np.dot(norm, l_fill)))
                    diff_rim = max(0.0, float(np.dot(norm, l_rim)))
                    base_r, base_g, base_b = 196, 148, 120
                    intensity = 0.25 + diff_key * 0.55 + diff_fill * 0.20
                    r_val = int(min(255, (base_r * intensity + diff_rim * 40) * dim))
                    g_val = int(min(255, (base_g * intensity + diff_rim * 70) * dim))
                    b_val = int(min(255, (base_b * intensity + diff_rim * 90) * dim))

                    poly = QPolygonF([QPointF(xs[ia], ys[ia]), QPointF(xs[ib], ys[ib]), QPointF(xs[ic], ys[ic])])
                    p.setBrush(QBrush(QColor(r_val, g_val, b_val)))
                    p.setPen(QPen(QColor(r_val // 2, g_val // 2, b_val // 2, 40), 0.5))
                    p.drawPolygon(poly)

                self._draw_facial_accents(p, xs, ys, dim)

        # ── Overlay Status Tag & Controls ──
        self._draw_status_tag(p, W, H)

    def _draw_ambient_fx(self, p: QPainter, cx: float, cy: float, rad: float):
        """Draws reactive halo, audio aura, and thinking particles."""
        amp = self.audio_level
        halo_rad = rad * (1.1 + amp * 0.15)

        # Halo colour based on state
        c_map = {
            "IDLE": QColor(0, 229, 255, 25),
            "LISTENING": QColor(16, 185, 129, 45),
            "THINKING": QColor(139, 92, 246, 50),
            "SPEAKING": QColor(56, 189, 248, 60),
            "EXECUTING": QColor(245, 158, 11, 45),
            "SUCCESS": QColor(16, 185, 129, 65),
            "ERROR": QColor(239, 68, 68, 45),
            "SLEEPING": QColor(30, 41, 59, 15),
        }
        halo_col = c_map.get(self.state, QColor(0, 229, 255, 25))

        glow = QRadialGradient(cx, cy, halo_rad)
        glow.setColorAt(0.0, halo_col)
        glow.setColorAt(0.5, QColor(halo_col.red(), halo_col.green(), halo_col.blue(), 10))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - halo_rad, cy - halo_rad, halo_rad * 2, halo_rad * 2))

        # Thinking / Executing orbital ring
        if self.state in ("THINKING", "EXECUTING"):
            p.save()
            p.translate(cx, cy)
            ring_angle = self._time * 120.0
            p.rotate(ring_angle)
            pen_col = QColor(139, 92, 246) if self.state == "THINKING" else QColor(245, 158, 11)
            p.setPen(QPen(pen_col, 1.8, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            r_ring = rad * 0.88
            p.drawEllipse(QRectF(-r_ring, -r_ring, r_ring * 2, r_ring * 2))
            p.restore()

    def _draw_facial_accents(self, p: QPainter, xs, ys, dim: float):
        """Draws expressive accents for lips, eyes, and eyebrows in mesh fallback mode."""
        p.setPen(QPen(QColor(int(28 * dim), int(22 * dim), int(24 * dim), 210), 2.2))
        for brow_key in ("brow_l", "brow_r"):
            pts = LANDMARKS.get(brow_key, [])
            for i in range(len(pts) - 1):
                i0, i1 = pts[i], pts[i+1]
                if i0 < len(xs) and i1 < len(xs):
                    p.drawLine(QPointF(xs[i0], ys[i0]), QPointF(xs[i1], ys[i1]))

        p.setPen(QPen(QColor(int(220 * dim), int(230 * dim), int(240 * dim), 160), 1.2))
        for eye_key in ("eye_l", "eye_r"):
            pts = LANDMARKS.get(eye_key, [])
            poly = QPolygonF([QPointF(xs[i], ys[i]) for i in pts if i < len(xs)])
            p.drawPolyline(poly)

        p.setPen(QPen(QColor(int(175 * dim), int(105 * dim), int(95 * dim), 190), 1.5))
        for lip_key in ("lip_out", "lip_in"):
            pts = LANDMARKS.get(lip_key, [])
            poly = QPolygonF([QPointF(xs[i], ys[i]) for i in pts if i < len(xs)])
            p.drawPolyline(poly)

    def _draw_status_tag(self, p: QPainter, W: int, H: int):
        """Draws top status badge and bottom branding."""
        badge_rect = QRectF(12, 12, 130, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(3, 10, 24, 180)))
        p.drawRoundedRect(badge_rect, 12, 12)

        c_dot = {
            "IDLE": QColor(0, 229, 255),
            "LISTENING": QColor(16, 185, 129),
            "THINKING": QColor(139, 92, 246),
            "SPEAKING": QColor(56, 189, 248),
            "EXECUTING": QColor(245, 158, 11),
            "SUCCESS": QColor(16, 185, 129),
            "ERROR": QColor(239, 68, 68),
            "SLEEPING": QColor(100, 116, 139),
        }.get(self.state, QColor(0, 229, 255))
        p.setBrush(QBrush(c_dot))
        p.drawEllipse(QRectF(22, 19, 8, 8))

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor(226, 232, 240))
        p.drawText(QRectF(36, 12, 100, 24), Qt.AlignmentFlag.AlignVCenter, self.state)

        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QColor(100, 116, 139, 170))
        p.drawText(QRectF(12, H - 24, W - 24, 16), Qt.AlignmentFlag.AlignLeft, "3D DIGITAL HUMAN · ADITYA")


class AvatarContainerWidget(QWidget):
    """
    Right Panel Avatar Container combining:
      - The 3D Digital Human Viewport
      - Quick Mode Toggles (WebGL Companion View / Native 3D Viewport)
      - Audio wave level readout
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # 3D Viewport
        self.viewport = Avatar3DViewport(self)
        lay.addWidget(self.viewport, stretch=1)

        # Controls bar under avatar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(6, 2, 6, 2)
        ctrl_bar.setSpacing(6)

        self._btn_webgl = QPushButton("🌐 3D WEBGL VIEW")
        self._btn_webgl.setFixedHeight(24)
        self._btn_webgl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self._btn_webgl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_webgl.setStyleSheet("""
            QPushButton {
                background: rgba(15, 23, 42, 0.7);
                color: #00e5ff;
                border: 1px solid rgba(0, 229, 255, 0.3);
                border-radius: 4px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.15);
                border-color: #00e5ff;
            }
        """)
        self._btn_webgl.clicked.connect(self._launch_webgl)
        ctrl_bar.addWidget(self._btn_webgl)

        self._btn_reset = QPushButton("⟲ RESET")
        self._btn_reset.setFixedHeight(24)
        self._btn_reset.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.setStyleSheet("""
            QPushButton {
                background: rgba(15, 23, 42, 0.7);
                color: #94a3b8;
                border: 1px solid rgba(148, 163, 184, 0.2);
                border-radius: 4px;
                padding: 2px 6px;
            }
            QPushButton:hover {
                background: rgba(148, 163, 184, 0.15);
                color: #e2e8f0;
            }
        """)
        self._btn_reset.clicked.connect(self.viewport.reset_view)
        ctrl_bar.addWidget(self._btn_reset)

        lay.addLayout(ctrl_bar)

    def _launch_webgl(self):
        avatar_server.launch_external_view()

    def set_state(self, state: str):
        self.viewport.set_state(state)

    def set_audio_level(self, level: float):
        self.viewport.set_audio_level(level)
