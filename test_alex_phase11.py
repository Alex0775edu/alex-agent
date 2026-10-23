"""
test_alex_phase11.py — Comprehensive Test Suite for ALEX Phase 11:
Double-Clap Activation & Smart Acoustic Wake System.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

import json
import math
import os
import sys
import time
import unittest
from pathlib import Path
import numpy as np

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.clap_detector import (
    ClapSettings,
    DoubleClapDetector,
    CLAP_CONFIG_FILE,
    SAMPLE_RATE,
    BLOCK_SIZE,
    play_chime_async,
)
from core.startup_manager import StartupManager, StartupSettings


# ── Acoustic Synthesis Helpers ───────────────────────────────────────────────

def generate_ambient_frame(samples: int = BLOCK_SIZE, rms_target: float = 150.0) -> np.ndarray:
    """Generate subtle Gaussian room noise."""
    noise = np.random.normal(0, rms_target, samples).astype(np.float32)
    return noise.astype(np.int16)


def generate_clap_frame(samples: int = BLOCK_SIZE, peak_amp: float = 12000.0) -> np.ndarray:
    """Generate sharp acoustic impulse: instantaneous rise time, exponential decay.

    Possesses high crest factor (> 4.5), distinct from harmonic speech.
    """
    decay = np.exp(-np.linspace(0, 15, samples))
    impulse = (peak_amp * decay * np.random.choice([1.0, -1.0], size=samples)).astype(np.float32)
    # Add minor background floor
    impulse += np.random.normal(0, 50, samples).astype(np.float32)
    return impulse.astype(np.int16)


def generate_speech_frame(samples: int = BLOCK_SIZE, amp: float = 8000.0) -> np.ndarray:
    """Generate speech-like harmonic sinusoidal waveform (vocal formant).

    Low crest factor (~1.4 - 2.0).
    """
    t = np.linspace(0, samples / SAMPLE_RATE, samples, endpoint=False)
    # Fundamental 220Hz + harmonics
    wave = amp * (0.6 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 880 * t))
    return wave.astype(np.int16)


class TestPhase11DoubleClap(unittest.TestCase):

    def setUp(self):
        # Reset settings to clean baseline
        self.settings = ClapSettings(
            enabled=True,
            sensitivity="medium",
            min_interval_ms=200,
            max_interval_ms=800,
            cooldown_ms=2000,
            sound_enabled=True,
            suppress_during_speech=True,
        )
        self.clap_triggers = 0
        self.peaks_detected = []

    def _on_clap(self):
        self.clap_triggers += 1

    def _on_peak(self, peak, crest):
        self.peaks_detected.append((peak, crest))

    def test_01_settings_persistence(self):
        """Test ClapSettings JSON persistence and reloading."""
        s = ClapSettings(enabled=True, sensitivity="high", min_interval_ms=250, max_interval_ms=750)
        det = DoubleClapDetector(settings=s)
        det.save_settings(s)

        loaded = DoubleClapDetector.load_settings()
        self.assertEqual(loaded.sensitivity, "high")
        self.assertEqual(loaded.min_interval_ms, 250)
        self.assertEqual(loaded.max_interval_ms, 750)

    def test_02_valid_double_clap_activation(self):
        """Two claps separated by 350ms should trigger activation."""
        det = DoubleClapDetector(
            on_double_clap=self._on_clap,
            on_peak_detected=self._on_peak,
            settings=self.settings,
        )

        t0 = 1000.0
        # 1. Warm ambient noise floor
        for i in range(10):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + i * 0.032)

        # 2. Clap 1 at t = 1000.500s
        t_clap1 = t0 + 0.500
        trig1 = det.process_frame(generate_clap_frame(), timestamp=t_clap1)
        self.assertFalse(trig1, "First clap should not trigger alone")
        self.assertEqual(self.clap_triggers, 0)

        # 3. Ambient frames during gap (350ms)
        for i in range(8):
            det.process_frame(generate_ambient_frame(), timestamp=t_clap1 + 0.032 * (i + 1))

        # 4. Clap 2 at t = 1000.850s (delta = 350ms)
        t_clap2 = t_clap1 + 0.350
        trig2 = det.process_frame(generate_clap_frame(), timestamp=t_clap2)
        self.assertTrue(trig2, "Second clap within 350ms window must trigger activation")
        self.assertEqual(self.clap_triggers, 1)

    def test_03_rejection_single_clap(self):
        """Single clap followed by silence should never activate."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 2000.0

        for i in range(5):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + i * 0.032)

        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.2)
        # Advance 1.5 seconds with ambient frames
        for i in range(40):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + 0.2 + (i + 1) * 0.032)

        self.assertEqual(self.clap_triggers, 0, "Single clap must not trigger activation")

    def test_04_rejection_too_fast_echo(self):
        """Two peaks separated by <200ms (reverberation/echo) must be rejected."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 3000.0

        for i in range(5):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + i * 0.032)

        # Clap 1
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.1)
        # Clap 2 only 90ms later (<200ms)
        trig = det.process_frame(generate_clap_frame(), timestamp=t0 + 0.190)
        self.assertFalse(trig, "Peak arriving at 90ms must be rejected as echo")
        self.assertEqual(self.clap_triggers, 0)

    def test_05_rejection_too_slow_window(self):
        """Two peaks separated by >800ms (e.g. 1.2s) should not trigger."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 4000.0

        for i in range(5):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + i * 0.032)

        # Clap 1
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.1)
        # Ambient during long silence
        for i in range(30):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + 0.1 + (i + 1) * 0.032)
        # Clap 2 at delta = 1.2s
        trig = det.process_frame(generate_clap_frame(), timestamp=t0 + 1.300)
        self.assertFalse(trig, "Peak arriving at 1200ms must not trigger (exceeds 800ms max window)")
        self.assertEqual(self.clap_triggers, 0)

    def test_06_false_trigger_speech_rejection(self):
        """Loud speech waveforms (harmonic formants) must be ignored."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 5000.0

        for i in range(5):
            det.process_frame(generate_ambient_frame(), timestamp=t0 + i * 0.032)

        # Feed 20 frames of continuous speech
        for i in range(20):
            trig = det.process_frame(generate_speech_frame(amp=9000.0), timestamp=t0 + 0.2 + i * 0.032)
            self.assertFalse(trig, "Speech formants must not trigger double clap")

        self.assertEqual(self.clap_triggers, 0)

    def test_07_cooldown_anti_chatter(self):
        """Claps within 2.0s cooldown window must be ignored."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 6000.0

        # Trigger 1st valid double clap
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.1)
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.45)
        self.assertEqual(self.clap_triggers, 1)

        # Immediate follow-up claps within 1 second (< 2.0s cooldown)
        trig1 = det.process_frame(generate_clap_frame(), timestamp=t0 + 0.8)
        trig2 = det.process_frame(generate_clap_frame(), timestamp=t0 + 1.2)
        self.assertFalse(trig1)
        self.assertFalse(trig2)
        self.assertEqual(self.clap_triggers, 1, "Cooldown must prevent repeated triggers")

    def test_08_speaker_feedback_suppression(self):
        """Clap detection is disabled while ALEX is actively speaking TTS."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 7000.0

        det.set_speaker_active(True)
        # Attempt double clap while speaker active
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.1)
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.45)
        self.assertEqual(self.clap_triggers, 0, "Speaker suppression must prevent self-activation")

        # Now speaker turns off
        det.set_speaker_active(False)
        det.process_frame(generate_clap_frame(), timestamp=t0 + 1.0)
        det.process_frame(generate_clap_frame(), timestamp=t0 + 1.4)
        self.assertEqual(self.clap_triggers, 1, "Detection resumes when speaker is inactive")

    def test_09_sensitivity_profiles(self):
        """Verify profile thresholds across low, medium, and high."""
        self.assertIn("low", DoubleClapDetector.SENSITIVITY_PROFILES)
        self.assertIn("medium", DoubleClapDetector.SENSITIVITY_PROFILES)
        self.assertIn("high", DoubleClapDetector.SENSITIVITY_PROFILES)

        # Low sensitivity requires highest peak
        self.assertGreater(
            DoubleClapDetector.SENSITIVITY_PROFILES["low"]["min_peak_abs"],
            DoubleClapDetector.SENSITIVITY_PROFILES["medium"]["min_peak_abs"]
        )
        self.assertGreater(
            DoubleClapDetector.SENSITIVITY_PROFILES["medium"]["min_peak_abs"],
            DoubleClapDetector.SENSITIVITY_PROFILES["high"]["min_peak_abs"]
        )

    def test_10_startup_background_mode(self):
        """Startup manager should support launch_minimized and --minimized flag."""
        sm = StartupManager.get_instance()
        exe_normal = sm.get_startup_executable(minimized=False)
        exe_min = sm.get_startup_executable(minimized=True)

        self.assertIn("main.py", exe_normal)
        self.assertIn("--minimized", exe_min)

    def test_11_dashboard_clap_api(self):
        """Test Dashboard clap settings loading, updating, and test endpoint."""
        det = DoubleClapDetector()
        det.update_settings(sensitivity="high", sound_enabled=True)
        s = det.load_settings()
        self.assertEqual(s.sensitivity, "high")
        self.assertTrue(s.sound_enabled)

    def test_12_timeline_integration(self):
        """Timeline records double clap activation action cleanly."""
        from core.action_timeline import timeline
        timeline.record(
            event_type="WAKE",
            title="Double clap detected",
            details="Test double clap event",
            status="SUCCESS",
            source="smart_wake"
        )
        recent = timeline.get_recent(limit=5)
        smart_wake_events = [e for e in recent if e.source == "smart_wake"]
        self.assertTrue(len(smart_wake_events) > 0)

    def test_13_end_to_end_wake_pipeline(self):
        """Simulate assistant sleeping, double-clap wakes it and requests window restore."""
        woken = False
        window_restored = False

        def mock_wake(reason=""):
            nonlocal woken
            woken = True

        def mock_restore():
            nonlocal window_restored
            window_restored = True

        def on_double_clap():
            mock_restore()
            mock_wake(reason="double clap")

        det = DoubleClapDetector(on_double_clap=on_double_clap, settings=self.settings)

        t0 = 8000.0
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.1)
        det.process_frame(generate_clap_frame(), timestamp=t0 + 0.45)

        self.assertTrue(woken, "Double clap must wake assistant")
        self.assertTrue(window_restored, "Double clap must restore window")

    def test_14_adaptive_noise_floor(self):
        """Elevated ambient noise dynamically raises noise floor and prevents false trigger."""
        det = DoubleClapDetector(on_double_clap=self._on_clap, settings=self.settings)
        t0 = 9000.0

        # Elevated ambient noise (e.g., fan noise at RMS 800)
        for i in range(20):
            det.process_frame(generate_ambient_frame(rms_target=800.0), timestamp=t0 + i * 0.032)

        self.assertGreater(det._ambient_rms, 300.0, "Ambient noise floor must adaptively rise")
    def test_15_ui_clap_drawer_controls(self):
        """Simulate UI drawer toggle actions on DoubleClapDetector settings."""
        det = DoubleClapDetector(settings=ClapSettings(enabled=True, sensitivity="medium", sound_enabled=True))
        det.save_settings(det.settings)

        # Toggle enabled
        s = DoubleClapDetector.load_settings()
        s.enabled = False
        det.save_settings(s)
        self.assertFalse(DoubleClapDetector.load_settings().enabled)

        # Cycle sensitivity medium -> high -> low -> medium
        cycle = {"low": "medium", "medium": "high", "high": "low"}
        s.sensitivity = cycle[s.sensitivity]
        det.save_settings(s)
        self.assertEqual(DoubleClapDetector.load_settings().sensitivity, "high")

        # Toggle chime
        s.sound_enabled = False
        det.save_settings(s)
        self.assertFalse(DoubleClapDetector.load_settings().sound_enabled)

        # Restore defaults
        s.enabled = True
        s.sensitivity = "medium"
        s.sound_enabled = True
        det.save_settings(s)


if __name__ == "__main__":
    unittest.main()
