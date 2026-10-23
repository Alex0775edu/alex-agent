"""
core/clap_detector.py — Real-time Acoustic Double-Clap Detector & Smart Wake System for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Key Architectural Principles:
  1. Transient Analysis: Uses rise-time, crest factor (peak-to-RMS ratio), and rapid decay
     to distinguish sharp acoustic impulses (claps) from speech and background noise.
  2. Adaptive Noise Floor: Dynamically tracks ambient room noise levels with an exponential
     moving average, avoiding static hardcoded volume thresholds.
  3. Precise Two-Peak Window: Validates that exactly two distinct transient impulses occur
     within the configurable temporal window (default 200ms - 800ms).
  4. Speaker Suppression & Echo Guard: Suppresses detection while ALEX or the system is playing TTS.
  5. Cooldown & Anti-Chatter: Configurable post-trigger refractory period (default 2.0s).
"""

from __future__ import annotations

import json
import math
import os
import queue
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CLAP_CONFIG_FILE = CONFIG_DIR / "clap_settings.json"

SAMPLE_RATE = 16000
BLOCK_SIZE = 512  # 32ms frames @ 16kHz for responsive temporal resolution


@dataclass
class ClapSettings:
    enabled: bool = True
    sensitivity: str = "medium"  # "low", "medium", "high"
    min_interval_ms: int = 200   # Claps closer than 200ms are treated as echoes/reverberations
    max_interval_ms: int = 800   # Max allowed separation between 1st and 2nd clap
    cooldown_ms: int = 2000      # Post-activation refractory period
    sound_enabled: bool = True   # Play subtle confirmation chime on activation
    suppress_during_speech: bool = True
    input_device: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def play_chime_async() -> None:
    """Plays subtle confirmation chime on Windows in background thread."""
    def _run():
        try:
            import winsound
            winsound.Beep(1046, 80)
            winsound.Beep(1318, 120)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True, name="AlexClapChimeThread").start()


class DoubleClapDetector:
    """Acoustic impulse detector that tracks ambient noise, computes transient crest factor,

    and validates two distinct clap peaks within a strict temporal window.
    """

    # Sensitivity parameter maps: (Peak/Noise Threshold, Crest Factor Threshold)
    SENSITIVITY_PROFILES = {
        "low": {"peak_ratio": 7.0, "crest_factor": 4.5, "min_peak_abs": 3500.0},
        "medium": {"peak_ratio": 4.5, "crest_factor": 3.4, "min_peak_abs": 2200.0},
        "high": {"peak_ratio": 3.0, "crest_factor": 2.6, "min_peak_abs": 1400.0},
    }

    def __init__(
        self,
        on_double_clap: Optional[Callable[[], None]] = None,
        on_peak_detected: Optional[Callable[[float, float], None]] = None,
        settings: Optional[ClapSettings] = None,
        logger: Callable[[str], None] = print,
    ):
        self._on_double_clap = on_double_clap
        self._on_peak_detected = on_peak_detected  # Test / diagnostic callback
        self._logger = logger
        self.settings = settings or self.load_settings()

        # Detection state
        self._first_clap_time: float = 0.0
        self._last_trigger_time: float = 0.0
        self._ambient_rms: float = 200.0  # Initial baseline
        self._alpha_noise: float = 0.05   # Smoothing factor for ambient noise floor
        self._is_speaker_active: bool = False
        self._test_mode: bool = False

        self._lock = threading.Lock()

    # ── Configuration Persistence ──────────────────────────────────────────

    @classmethod
    def load_settings(cls) -> ClapSettings:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CLAP_CONFIG_FILE.exists():
            try:
                data = json.loads(CLAP_CONFIG_FILE.read_text(encoding="utf-8"))
                return ClapSettings(**data)
            except Exception:
                pass
        return ClapSettings()

    def save_settings(self, settings: ClapSettings) -> None:
        self.settings = settings
        CLAP_CONFIG_FILE.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")

    def update_settings(self, **kwargs) -> None:
        cur = self.settings.to_dict()
        cur.update(kwargs)
        self.save_settings(ClapSettings(**cur))

    # ── Feedback & Echo Guard ──────────────────────────────────────────────

    def set_speaker_active(self, active: bool) -> None:
        """Suppresses clap detection while ALEX is outputting TTS speech."""
        with self._lock:
            self._is_speaker_active = active

    def set_test_mode(self, enabled: bool) -> None:
        """In test mode, peaks and claps are logged/reported without triggering actual activation."""
        self._test_mode = enabled

    # ── Real-Time Audio Frame Processing ───────────────────────────────────

    def process_frame(self, frame_int16: np.ndarray, timestamp: Optional[float] = None) -> bool:
        """Process a single PCM frame (16-bit integer, mono or stereo).

        Returns True if a valid double-clap trigger occurred on this frame.
        """
        if not self.settings.enabled:
            return False

        now = timestamp if timestamp is not None else time.monotonic()

        # Check speaker suppression (TTS active)
        if self.settings.suppress_during_speech and self._is_speaker_active:
            return False

        # Check post-activation cooldown
        cooldown_sec = self.settings.cooldown_ms / 1000.0
        if (now - self._last_trigger_time) < cooldown_sec:
            return False

        # Convert to 1D float array
        if getattr(frame_int16, "ndim", 1) > 1:
            samples = frame_int16[:, 0].astype(np.float32)
        else:
            samples = frame_int16.astype(np.float32)

        if samples.size == 0:
            return False

        # Signal features
        peak_val = float(np.max(np.abs(samples)))
        rms_val = float(np.sqrt(np.mean(samples ** 2))) + 1e-6
        crest_factor = peak_val / rms_val

        profile = self.SENSITIVITY_PROFILES.get(self.settings.sensitivity, self.SENSITIVITY_PROFILES["medium"])
        min_peak = profile["min_peak_abs"]
        min_peak_ratio = profile["peak_ratio"]
        min_crest = profile["crest_factor"]

        # Adaptively update ambient noise floor during non-transient frames
        if crest_factor < min_crest or peak_val < (self._ambient_rms * 2.0):
            self._ambient_rms = (1.0 - self._alpha_noise) * self._ambient_rms + self._alpha_noise * rms_val

        # Temporal decay asymmetry (claps decay sharply, while noise and speech have uniform energy)
        half = max(1, samples.size // 2)
        head_rms = float(np.sqrt(np.mean(samples[:half] ** 2))) + 1e-6
        tail_rms = float(np.sqrt(np.mean(samples[half:] ** 2))) + 1e-6
        temporal_asymmetry = max(head_rms / tail_rms, tail_rms / head_rms)

        # Check transient characteristics:
        # A clap must exceed absolute amplitude, exceed ambient floor by ratio,
        # possess a high crest factor, and show sharp temporal decay asymmetry.
        is_transient = (
            peak_val >= min_peak and
            (peak_val / max(self._ambient_rms, 10.0)) >= min_peak_ratio and
            crest_factor >= min_crest and
            temporal_asymmetry >= 1.5
        )

        if not is_transient:
            # Check if previous clap timed out
            max_window_sec = self.settings.max_interval_ms / 1000.0
            if self._first_clap_time > 0 and (now - self._first_clap_time) > max_window_sec:
                self._first_clap_time = 0.0
            return False

        # Transient peak detected!
        if self._on_peak_detected:
            self._on_peak_detected(peak_val, crest_factor)

        min_window_sec = self.settings.min_interval_ms / 1000.0
        max_window_sec = self.settings.max_interval_ms / 1000.0

        if self._first_clap_time == 0.0:
            # First clap candidate
            self._first_clap_time = now
            return False
        else:
            delta = now - self._first_clap_time

            # Too fast (echo/reverberation of first clap)
            if delta < min_window_sec:
                return False

            # Within valid interval (200ms - 800ms)!
            if min_window_sec <= delta <= max_window_sec:
                self._first_clap_time = 0.0
                self._last_trigger_time = now
                self._logger(f"[SmartWake] [CLAP-CLAP] DOUBLE CLAP DETECTED! Delta: {delta * 1000:.1f}ms (Peak: {peak_val:.0f})")

                if self.settings.sound_enabled:
                    play_chime_async()

                if not self._test_mode and self._on_double_clap:
                    self._on_double_clap()

                return True
            else:
                # Outside max window: treat current peak as new first clap
                self._first_clap_time = now
                return False

    def reset(self) -> None:
        """Reset internal detection state."""
        self._first_clap_time = 0.0
        self._last_trigger_time = 0.0


class ClapListenerThread(threading.Thread):
    """Dedicated background audio listener thread for double-clap detection.

    Runs when ALEX is asleep, minimized, or in background startup mode.
    Releases audio resources cleanly upon stopping.
    """

    def __init__(
        self,
        detector: DoubleClapDetector,
        sample_rate: int = SAMPLE_RATE,
        block_size: int = BLOCK_SIZE,
        device: Optional[int] = None,
        logger: Callable[[str], None] = print,
    ):
        super().__init__(daemon=True, name="AlexClapListenerThread")
        self.detector = detector
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self._logger = logger
        self._stop_event = threading.Event()
        self._stream = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def run(self) -> None:
        import sounddevice as sd

        def audio_callback(indata, frames, time_info, status):
            if self._stop_event.is_set():
                raise sd.CallbackStop()
            self.detector.process_frame(indata)

        device_target = self.device if self.device is not None else self.detector.settings.input_device
        self._logger(f"[SmartWake] Starting background clap listener (device={device_target}, rate={self.sample_rate})...")

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=device_target,
                channels=1,
                dtype="int16",
                callback=audio_callback,
            ) as stream:
                self._stream = stream
                while not self._stop_event.is_set():
                    time.sleep(0.05)
        except Exception as e:
            self._logger(f"[SmartWake] Background audio listener ended: {e}")
        finally:
            self._stream = None
            self._logger("[SmartWake] Background audio listener stopped.")
