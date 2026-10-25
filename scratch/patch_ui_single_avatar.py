"""
patch_ui_single_avatar.py — Updates ui.py to ensure exactly ONE active 3D avatar
and fully retires the old wireframe HoloAvatar from active rendering.
"""

from pathlib import Path

ui_path = Path("ui.py")
text = ui_path.read_text(encoding="utf-8")

# 1. Update HudCanvas.__init__ to retire old HoloAvatar
old_init_needle = """        self._avatar = None
        if HoloAvatar is not None:
            try:
                self._avatar = HoloAvatar()
            except Exception:
                self._avatar = None

        # Which centrepiece to draw. Read once here and changed live by the
        # settings toggle; the avatar object is kept either way so switching
        # back is instant and costs no reload.
        try:
            from memory.config_manager import get_hud_style
            self.hud_style = get_hud_style()
        except Exception:
            self.hud_style = "face"
        self._core_phase = 0.0"""

new_init_replacement = """        # The old wireframe HoloAvatar has been retired from active rendering
        # so that ALEX features exactly ONE authentic 3D digital human avatar.
        self._avatar = None
        self.hud_style = "core"
        self._core_phase = 0.0"""

# Normalize CRLF/LF
text_norm = text.replace("\r\n", "\n")
old_init_norm = old_init_needle.replace("\r\n", "\n")

if old_init_norm in text_norm:
    text_norm = text_norm.replace(old_init_norm, new_init_replacement)
    print("Step 1: Successfully replaced old HoloAvatar initialization in HudCanvas!")
else:
    print("Warning: old_init_needle not found, checking lines...")
    lines = text_norm.splitlines()
    for i, l in enumerate(lines[:500]):
        if "self._avatar = None" in l and i < 450:
            print(f"Found at line {i+1}: {l}")

# 2. Update HudCanvas.paintEvent to eliminate drawing the old wireframe avatar face
old_paint_needle = """        _sy_status = cy + fw * 0.40
        if self._avatar is not None and self.hud_style == "face":
            _band_t = 12.0
            _band_h = max(60.0, _sy_status - 12.0 - _band_t)
            _r_head = min(fw * 0.355, _band_h / (self._avatar.SPAN + 0.08))
            _head_cy = _band_t + (_band_h - self._avatar.SPAN * _r_head) / 2.0 + _r_head

            if self.muted:
                _main = _acc = qcol(C.MUTED_C)
            else:
                _main = qcol(C.PRI)
                if self.speaking:
                    _acc = qcol(C.ACC)
                elif self.state in ("THINKING", "PROCESSING"):
                    _acc = qcol(C.ACC2)
                elif self.state == "LISTENING":
                    _acc = qcol(C.GREEN)
                else:
                    _acc = qcol(C.PRI)
            self._avatar.paint(p, cx, _head_cy, _r_head, _main, _acc, qcol(C.BG))

        # reactor core — the other centrepiece, and the fallback if the head
        # could not be built. There is no third path: the old face.png branch
        # was unreachable (no such file ships) and the bare orb it fell through
        # to is what this replaces.
        else:
            _band_t = 12.0
            _band_h = max(60.0, _sy_status - 12.0 - _band_t)
            _r = min(W * 0.46, _band_h / 2.0)
            self._paint_core(p, cx, _band_t + _band_h / 2.0, _r, W, _band_h)"""

new_paint_replacement = """        # ── Central HUD Telemetry (The single 3D avatar renders in the dedicated right viewport) ──
        _sy_status = cy + fw * 0.40
        _band_t = 12.0
        _band_h = max(60.0, _sy_status - 12.0 - _band_t)
        _r = min(W * 0.46, _band_h / 2.0)
        self._paint_core(p, cx, _band_t + _band_h / 2.0, _r, W, _band_h)"""

old_paint_norm = old_paint_needle.replace("\r\n", "\n")
if old_paint_norm in text_norm:
    text_norm = text_norm.replace(old_paint_norm, new_paint_replacement)
    print("Step 2: Successfully retired old face painting in HudCanvas.paintEvent!")
else:
    print("Warning: old_paint_needle not found")

# 3. Ensure _do_interrupt informs avatar_bridge
old_interrupt = """    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()"""

new_interrupt = """    def _do_interrupt(self):
        if avatar_bridge is not None:
            avatar_bridge.interrupt()
        if self.on_interrupt:
            self.on_interrupt()"""

old_int_norm = old_interrupt.replace("\r\n", "\n")
if old_int_norm in text_norm:
    text_norm = text_norm.replace(old_int_norm, new_interrupt)
    print("Step 3: Successfully linked _do_interrupt with avatar_bridge.interrupt()!")

ui_path.write_text(text_norm, encoding="utf-8")
print("Saved patched ui.py!")

