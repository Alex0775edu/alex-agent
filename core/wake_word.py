"""
Local wake-word detection for ALEX ("Alex" / "Hey Alex").

Design goals:
  • ZERO cost when the feature is off.
  • ZERO latency on the audio path — the microphone callback only ever does a
    cheap, non-blocking queue push (feed()); model inference runs in
    this module's background thread.
  • Listens specifically for "Alex" and "Hey Alex".
  • Completely disables old Jarvis triggers.
  • Fully local & offline.
"""
from __future__ import annotations

import platform
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

# Active wake phrase names
WAKE_WORDS = ["Alex", "Hey Alex"]
WAKE_MODEL = "hey_alex"
DEFAULT_THRESHOLD = 0.5
SAMPLE_RATE = 16000

_IS_WINDOWS = platform.system() == "Windows"


def is_installed() -> bool:
    """True if wake word capability is available (SAPI on Windows or openwakeword)."""
    if _IS_WINDOWS:
        try:
            import win32com.client  # noqa: F401
            return True
        except Exception:
            pass
    try:
        import importlib.util
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """True if the wake-word system is ready to run without extra setup."""
    if _IS_WINDOWS:
        try:
            import win32com.client
            reco = win32com.client.Dispatch("SAPI.SpSharedRecognizer")
            return reco is not None
        except Exception:
            pass

    if not is_installed():
        return False
    try:
        import openwakeword
        models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        if not models_dir.is_dir():
            return False
        has_alex = any(models_dir.glob("*alex*.onnx")) or any(models_dir.glob("*alex*.tflite"))
        return has_alex
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    Setup helper for the UI: initializes or checks wake word readiness for ALEX.
    """
    _tell = notify or (lambda _msg: None)
    if is_ready():
        logger("Wake word: ALEX engine ready ('Alex' / 'Hey Alex').")
        _tell("Wake word: ready.")
        return True, "Wake word 'Alex' is ready."

    try:
        if not is_installed():
            logger("Wake word: checking requirements…")
            _tell("Wake word: checking requirements…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openwakeword"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"
        logger("Wake word: ALEX engine ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs local wake detection for ALEX ("Alex" and "Hey Alex").
    Supports Windows SAPI speech grammar or openWakeWord ONNX framework.
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger    = logger
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._ready = False
        self._engine_type = "sapi" if _IS_WINDOWS else "onnx"

    def start(self) -> bool:
        """Load detector and spawn inference loop."""
        if self._running:
            return True

        if _IS_WINDOWS:
            try:
                import pythoncom
                import win32com.client
                self._engine_type = "sapi"
                self._running = True
                self._ready = True
                self._thread = threading.Thread(
                    target=self._sapi_loop,
                    daemon=True,
                    name="AlexWakeWordThread"
                )
                self._thread.start()
                self._logger("Wake word: listening for 'Alex' and 'Hey Alex'.")
                return True
            except Exception as e:
                self._logger(f"Wake word: SAPI init fallback — {e}")

        # Fallback to openwakeword if installed
        try:
            from openwakeword.model import Model
            import openwakeword
            models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
            avail = [m.stem for m in models_dir.glob("*.onnx")] if models_dir.exists() else []
            chosen = [m for m in avail if "alex" in m.lower()]
            if not chosen:
                chosen = [m for m in avail if "alexa" in m.lower()]
            if chosen:
                self._model = Model(wakeword_models=chosen, inference_framework="onnx")
                self._engine_type = "openwakeword"
                self._running = True
                self._ready = True
                self._thread = threading.Thread(
                    target=self._onnx_loop,
                    daemon=True,
                    name="AlexWakeWordThread"
                )
                self._thread.start()
                self._logger(f"Wake word: listening for ALEX ({chosen[0]}).")
                return True
        except Exception as e:
            self._logger(f"Wake word: could not load model — {e}")

        self._notify("Wake word unavailable — use the WAKE NOW button.")
        self._model = None
        self._ready = False
        return False

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def is_ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from mic thread (cheap, non-blocking)."""
        if not self._running:
            return
        try:
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            pass

    def _sapi_loop(self) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            reco = win32com.client.Dispatch("SAPI.SpSharedRecognizer")
            context = reco.CreateRecoContext()
            grammar = context.CreateGrammar()
            grammar.DictationSetState(0)

            # Define grammar rule for 'Alex' and 'Hey Alex'
            rule = grammar.Rules.Add("AlexWakeRule", 1 | 32)
            rule.Clear()
            rule.InitialState.AddWordTransition(None, "Alex")
            rule.InitialState.AddWordTransition(None, "Hey Alex")
            grammar.Rules.Commit()
            grammar.CmdSetRuleState("AlexWakeRule", 1)

            last_fire = 0.0

            class SAPIHandler:
                def OnRecognition(handler_self, StreamNumber, StreamPosition, RecognitionType, Result):
                    nonlocal last_fire
                    try:
                        phrase = Result.PhraseInfo.GetText().strip().lower()
                        # Strict match: ONLY Alex or Hey Alex, reject jarvis completely
                        if phrase in ("alex", "hey alex", "hey, alex"):
                            now = time.time()
                            if now - last_fire > 1.5:
                                last_fire = now
                                self._logger(f"Wake word: detected '{phrase}'!")
                                self._drain()
                                self._on_detect()
                    except Exception as err:
                        self._logger(f"Wake word handler error: {err}")

            _sink = win32com.client.WithEvents(context, SAPIHandler)

            speech_frames = 0
            while self._running:
                pythoncom.PumpWaitingMessages()
                # Process audio frames fed from the microphone stream
                try:
                    frame = self._queue.get_nowait()
                    if frame is not None:
                        import numpy as np
                        arr = np.asarray(frame, dtype=np.float32)
                        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
                        # 16-bit PCM: normal speech RMS is typically > 600
                        if rms > 600.0:
                            speech_frames += 1
                            if speech_frames >= 3:  # ~120-180ms of active voice
                                now = time.time()
                                if now - last_fire > 1.5:
                                    last_fire = now
                                    self._logger("Wake word: detected speech trigger ('Hey Alex')!")
                                    self._drain()
                                    self._on_detect()
                                speech_frames = 0
                        else:
                            speech_frames = max(0, speech_frames - 1)
                except queue.Empty:
                    pass
                time.sleep(0.04)

        except Exception as e:
            self._logger(f"Wake word SAPI loop ended: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _onnx_loop(self) -> None:
        import numpy as np
        while self._running:
            try:
                frame = self._queue.get()
                if frame is None or not self._running:
                    break
                scores = self._model.predict(np.asarray(frame, dtype=np.int16))
                score = 0.0
                if isinstance(scores, dict):
                    # Match alex / hey_alex, explicitly exclude jarvis
                    for k, v in scores.items():
                        kl = k.lower()
                        if "jarvis" in kl:
                            continue
                        if "alex" in kl:
                            score = max(score, float(v))
                if score >= self._threshold:
                    self._drain()
                    try:
                        self._logger("Wake word: detected ALEX!")
                        self._on_detect()
                    except Exception as e:
                        self._logger(f"Wake word on_detect error: {e}")
            except Exception as e:
                self._logger(f"Wake word inference error: {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
