"""
core/avatar_service.py — Isolated WebGL Avatar Server & Lifecycle Manager.

Hosts the Three.js 3D avatar application on a local loopback port,
manages optional embedded WebView / browser subprocess, and keeps
the 3D renderer completely isolated from the core assistant logic.
"""

from __future__ import annotations

import functools
import http.server
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("alex.avatar_service")

BASE_DIR = Path(__file__).resolve().parent.parent
AVATAR_STATIC = BASE_DIR / "dashboard" / "static" / "avatar"
DEFAULT_AVATAR_PORT = 8765


class _QuietAvatarHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the 3D avatar static files without noisy console logging."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(AVATAR_STATIC), **kwargs)

    def log_message(self, format, *args):
        # Silence per-asset HTTP logs to keep ALEX console clean
        pass

    def end_headers(self):
        # Add CORS and no-cache headers for instant asset updates
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()


class AvatarServerManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.server: http.server.ThreadingHTTPServer | None = None
        self.port: int = DEFAULT_AVATAR_PORT
        self.running: bool = False
        self._server_thread: threading.Thread | None = None
        self._browser_proc: subprocess.Popen | None = None

    @classmethod
    def get_instance(cls) -> AvatarServerManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = AvatarServerManager()
            return cls._instance

    def _find_free_port(self, start_port: int = 8765) -> int:
        for p in range(start_port, start_port + 20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", p)) != 0:
                    return p
        return start_port

    def start_server(self) -> int:
        """Start the background HTTP server for Three.js assets."""
        if self.running and self.server:
            return self.port

        self.port = self._find_free_port(DEFAULT_AVATAR_PORT)
        try:
            handler = _QuietAvatarHandler
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), handler)
            self.running = True
            self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._server_thread.start()
            logger.info("Avatar 3D HTTP service running on http://127.0.0.1:%d", self.port)
        except Exception as e:
            logger.warning("Could not start dedicated avatar server: %s", e)
        return self.port

    def get_avatar_url(self) -> str:
        self.start_server()
        return f"http://127.0.0.1:{self.port}/index.html"

    def launch_external_view(self) -> bool:
        """Launches an isolated borderless 3D viewport companion."""
        url = self.get_avatar_url()
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_exe = next((p for p in edge_paths if os.path.exists(p)), None)
        if not edge_exe:
            return False

        profile_dir = BASE_DIR / ".avatar_profile"
        try:
            self._browser_proc = subprocess.Popen([
                edge_exe,
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--window-size=440,560",
                "--no-first-run",
                "--no-default-browser-check"
            ])
            return True
        except Exception as e:
            logger.error("Failed to launch external 3D avatar viewport: %s", e)
            return False

    def shutdown(self):
        if self._browser_proc:
            try:
                self._browser_proc.terminate()
            except Exception:
                pass
            self._browser_proc = None

        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass
            self.running = False


avatar_server = AvatarServerManager.get_instance()
