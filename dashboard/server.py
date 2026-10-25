"""
dashboard/server.py — ALEX Local HTTP Dashboard

Plain HTTP on port 8000 (no SSL warnings, no firewall issues).
Security at the application layer: AES-256-CBC with session-key-derived key.
CryptoJS is auto-downloaded once and served locally — no CDN needed after that.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import time
from pathlib import Path

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

# python-multipart is required for file uploads — optional dependency
_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
PORT        = 8000
MAX_UPLOAD_MB = 500


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "ALEX Uploads",
        Path.home() / "Documents" / "ALEX Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'ALEX-DASHBOARD-v2'
_LEGACY_AES_SALT = b'JARVIS-DASHBOARD-v1'


def _derive_key(session_key: str, salt: bytes = _AES_SALT) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed)."""
    return hashlib.sha256(session_key.encode('utf-8') + salt).digest()


def _decrypt_cbc(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_pad
    raw      = base64.b64decode(enc_b64)
    iv, ct   = raw[:16], raw[16:]
    dec      = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded   = dec.update(ct) + dec.finalize()
    unpadder = sym_pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


# ── CryptoJS (auto-download once, served locally) ─────────────────────────────
_CRYPTOJS_CDN  = ("https://cdnjs.cloudflare.com/ajax/libs/"
                  "crypto-js/4.2.0/crypto-js.min.js")
_CRYPTOJS_FILE = STATIC_DIR / "crypto-js.min.js"


def _ensure_network_access(port: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread — never blocks uvicorn startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys, subprocess, os, tempfile, threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes, time

        port_rule = f"ALEX Dashboard Port {port}"
        prog_rule  = "ALEX Dashboard Python"
        py_exe     = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port    = not _netsh_rule_exists(port_rule)
        need_prog    = not _netsh_rule_exists(prog_rule)
        need_private = _network_is_public()

        if not need_port and not need_prog and not need_private:
            return  # already fully configured

        # Build a .bat file — netsh + powershell, runs fast when elevated
        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="alex_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))   # Windows cmd.exe expects ANSI
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        # ── Try running directly (succeeds when already admin) ────────────────
        try:
            r = subprocess.run(
                [bat_path], capture_output=True, timeout=8, shell=True
            )
            if r.returncode == 0:
                print(f"[Dashboard] Firewall configured for port {port}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Non-intrusive LAN setup: Do not interrupt Aditya Sir with UAC popups on normal launch
        try:
            if os.path.exists(bat_path):
                os.unlink(bat_path)
        except Exception:
            pass
        finally:
            # Cleanup after the bat has had time to run
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return  # firewall off — nothing to do

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, timeout=5,
            )
            if py in listed.stdout:
                return  # already allowed

            print("[Dashboard] One-time network setup — enter your password in the macOS dialog.")
            subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except Exception:
            pass  # macOS firewall is off by default — silent failure is fine
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    try:  # ufw
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        if "active" in r.stdout.lower():
            if _privileged(["ufw", "allow", f"{port}/tcp"]):
                print(f"[Dashboard] ufw: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:  # firewalld
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5,
        )
        if "running" in r.stdout.lower():
            ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                  and _privileged(["firewall-cmd", "--reload"]))
            if ok:
                print(f"[Dashboard] firewalld: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:  # iptables (not persistent but works until reboot)
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                print(f"[Dashboard] iptables: port {port} opened.")
            else:
                print(f"[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do


def _ensure_crypto_js() -> None:
    if _CRYPTOJS_FILE.exists():
        return
    try:
        import urllib.request
        print("[Dashboard] Downloading CryptoJS (one-time setup)…")
        urllib.request.urlretrieve(_CRYPTOJS_CDN, str(_CRYPTOJS_FILE))
        print("[Dashboard] CryptoJS cached — will serve locally from now on.")
    except Exception as e:
        print(f"[Dashboard] CryptoJS download failed: {e}")
        print(f"[Dashboard] Encryption will fall back to CDN load on client.")


_ensure_crypto_js()


# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""
    # Method 1: route trick (fast, works when internet is available)
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # Method 2: hostname resolution (works offline on most systems)
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Method 3: enumerate all interfaces (fully offline, no external deps)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def _ensure_certs() -> bool:
    """
    Make sure config/certs holds a TLS key pair, generating a self-signed one the
    first time the dashboard runs.

    The pair is deliberately NOT shipped in the repository. A private key that
    every user downloads is the same as having no private key at all: anyone can
    present a certificate that matches it. Generating locally gives each install
    its own key, costs about a second, and happens exactly once.

    Returns True when a usable pair exists afterwards; False leaves the caller on
    plain HTTP, which still works — the QR code simply encodes http:// instead.
    """
    certs = BASE_DIR / "config" / "certs"
    key_p = certs / "alex.key"
    crt_p = certs / "alex.crt"
    if not (key_p.exists() and crt_p.exists()):
        key_p = certs / "jarvis.key"
        crt_p = certs / "jarvis.crt"
    if key_p.exists() and crt_p.exists():
        return True

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("[Dashboard] cryptography not installed — serving over plain HTTP.")
        print("[Dashboard] For HTTPS run:  pip install cryptography")
        return False

    try:
        certs.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        who = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "ALEX Dashboard"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ALEX"),
        ])

        # The SAN has to cover every address the phone might use: the LAN IP the
        # QR code encodes, plus localhost when testing on the machine itself.
        alt = [x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
        try:
            lan = _local_ip()
            if not lan.startswith("127."):
                alt.append(x509.IPAddress(ipaddress.IPv4Address(lan)))
        except Exception:
            pass          # no LAN address resolvable — localhost entries still work

        # Timezone-aware UTC: datetime.utcnow() is deprecated from Python 3.12 on,
        # and the builder normalises aware values to UTC itself.
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(who)
            .issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        key_p.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        try:
            import os as _os
            _os.chmod(key_p, 0o600)   # best effort — largely a no-op on Windows
        except Exception:
            pass

        print(f"[Dashboard] Generated a self-signed certificate for this machine: {certs}")
        return True
    except Exception as e:
        print(f"[Dashboard] Certificate generation failed ({e}) — serving over plain HTTP.")
        return False


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


# ── DashboardServer ───────────────────────────────────────────────────────────

class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        self._tokens: set[str]            = set()
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._pending_keys: dict[str, float] = {}
        self._device_sessions: dict[str, dict] = {}  # device_token → {session_key}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._uploads_dir                 = UPLOADS_DIR
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        certs = BASE_DIR / "config" / "certs"
        has_alex = (certs / "alex.key").exists() and (certs / "alex.crt").exists()
        has_jarvis = (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()
        return has_alex or has_jarvis

    def get_url(self) -> str:
        proto = "https" if self._ssl_enabled() else "http"
        return f"{proto}://{self._ip}:{PORT}"

    def get_manual_url(self) -> str:
        """URL for manual browser entry. When HTTPS active, points to alias port (also HTTPS)."""
        if self._ssl_enabled():
            return f"{self._ip}:{PORT + 1}"
        return f"{self._ip}:{PORT}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt_cbc(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _auth(req: Request) -> bool:
            tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            return bool(tok) and tok in self._tokens

        # Serve 3D Digital Human Avatar
        @app.get("/avatar", response_class=HTMLResponse)
        async def avatar_index():
            f_path = STATIC_DIR / "avatar" / "index.html"
            if f_path.exists():
                return HTMLResponse(f_path.read_text(encoding="utf-8"))
            return HTMLResponse("<h3>3D Avatar view not found</h3>", status_code=404)

        @app.get("/avatar/{file_path:path}")
        async def serve_avatar_assets(file_path: str):
            f_path = STATIC_DIR / "avatar" / (file_path or "index.html")
            if f_path.is_dir():
                f_path = f_path / "index.html"
            if f_path.exists():
                return FileResponse(str(f_path))
            return JSONResponse({"error": "Avatar asset not found"}, status_code=404)

        # serve CryptoJS from local cache, fallback to CDN redirect
        @app.get("/static/crypto.js")
        async def serve_crypto():
            if _CRYPTOJS_FILE.exists():
                return FileResponse(str(_CRYPTOJS_FILE),
                                    media_type="application/javascript")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(_CRYPTOJS_CDN)

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            # Auth is handled client-side via sessionStorage bearer token.
            # Server-side header auth can't work here because browser navigations
            # don't send custom headers (location.href doesn't carry Authorization).
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return HTMLResponse(html)

        @app.post("/login")
        async def login(req: Request):
            body    = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                del self._pending_keys[entered]          # one-time use
                tok = secrets.token_urlsafe(32)
                self._tokens.add(tok)
                self._token_keys[tok] = entered
                self._aes_key(entered)                   # pre-derive & cache
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#dde3ed">Remote Control</strong> in ALEX to get a new QR code.</p>
</div></body></html>""")

            del self._pending_keys[key]
            tok     = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('alex_token','{tok}');
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('alex_key','{key}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('alex_device_token','{dev_tok}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to ALEX…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = session_key
            self._aes_key(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            count = len(self._device_sessions)
            self._device_sessions.clear()
            return JSONResponse({"ok": True, "revoked": count})

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body  = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()
            if text:
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        # ── Double-Clap & Smart Wake API Endpoints ────────────────────────────

        @app.get("/api/clap/settings")
        async def get_clap_settings_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.clap_detector import DoubleClapDetector
                settings = DoubleClapDetector.load_settings()
                return JSONResponse({"ok": True, "settings": settings.to_dict()})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @app.post("/api/clap/settings")
        async def update_clap_settings_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.clap_detector import DoubleClapDetector, ClapSettings
                body = await req.json()
                s = DoubleClapDetector.load_settings()
                d = s.to_dict()
                d.update(body)
                new_settings = ClapSettings(**d)
                det = DoubleClapDetector(settings=new_settings)
                det.save_settings(new_settings)
                return JSONResponse({"ok": True, "settings": new_settings.to_dict()})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @app.post("/api/clap/test")
        async def test_clap_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.clap_detector import play_chime_async
                from core.action_timeline import timeline
                timeline.record(
                    event_type="WAKE",
                    title="Double clap test",
                    details="Test double clap triggered via Dashboard.",
                    status="SUCCESS",
                    source="smart_wake",
                )
                play_chime_async()
                if self._wake_callback:
                    self._wake_callback()
                return JSONResponse({"ok": True, "message": "Double clap test triggered and wake executed."})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        # ── Phase 2: Autonomous Execution & Project Health Endpoints ──────────

        @app.get("/api/project/health")
        async def get_project_health_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.project_health import ProjectHealthInspector
                report = ProjectHealthInspector.inspect()
                return JSONResponse({"ok": True, "health": report.to_dict()})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @app.get("/api/tools")
        async def list_tools_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.tool_registry import tool_registry
                tools = tool_registry.list_tools()
                return JSONResponse({"ok": True, "tools": tools})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @app.post("/api/execution/goal")
        async def execute_goal_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.execution_engine import execution_engine
                body = await req.json()
                request_text = body.get("request", "").strip()
                if not request_text:
                    return JSONResponse({"ok": False, "error": "Request text is required."}, status_code=400)
                project_path = body.get("project_path")
                # Run synchronous or background
                run_bg = body.get("background", False)
                if run_bg:
                    tid = execution_engine.start_goal_background(request_text, project_path)
                    return JSONResponse({"ok": True, "task_id": tid, "status": "QUEUED_BACKGROUND"})
                else:
                    res = execution_engine.execute_goal_sync(request_text, project_path)
                    return JSONResponse({"ok": True, "result": res})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @app.post("/api/execution/task-action")
        async def task_action_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                from core.execution_engine import execution_engine
                body = await req.json()
                task_id = body.get("task_id", "")
                action = body.get("action", "").lower()
                if action == "pause":
                    ok, msg = execution_engine.pause_task(task_id)
                elif action == "resume":
                    ok, msg = execution_engine.resume_task(task_id)
                elif action == "cancel":
                    ok, msg = execution_engine.cancel_task(task_id)
                else:
                    return JSONResponse({"ok": False, "error": f"Unknown action: {action}"}, status_code=400)
                return JSONResponse({"ok": ok, "message": msg})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Phone microphone live."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        def _safe_filename(raw: str) -> str:
            name = Path(raw).name                          # strip path components
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
            return name or "upload"

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/briefing")
        async def get_briefing(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.startup_manager import startup_manager
            data = startup_manager.generate_full_briefing(is_startup=False)
            return JSONResponse({"ok": True, "briefing": data})

        @app.get("/api/news")
        async def get_news(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.news_engine import news_intelligence
            from dataclasses import asdict
            items = news_intelligence.fetch_top_news()
            return JSONResponse({"ok": True, "news": [asdict(it) for it in items]})

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/api/system-overview")
        async def get_system_overview(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            import psutil, os, sys
            from core.security import security_manager, OWNER_NAME, OWNER_ADDRESS
            from core.task_center import task_center
            from core.action_timeline import timeline
            from core.project_manager import project_manager
            from core.proactive_intelligence import proactive_engine
            from core.service_manager import service_manager
            from core.clap_detector import DoubleClapDetector
            from core.project_health import ProjectHealthInspector
            from dataclasses import asdict

            clap_settings = DoubleClapDetector.load_settings()

            vm = psutil.virtual_memory()
            drive_letter = os.path.splitdrive(sys.executable)[0] or "C:"
            try:
                du = psutil.disk_usage(drive_letter)
                disk_pct = du.percent
                disk_free = round(du.free / (1024**3), 1)
            except Exception:
                disk_pct = 0
                disk_free = 0

            cpu = psutil.cpu_percent(interval=None)

            gpu_info = "None (CPU Mode)"
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                gpu_name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(gpu_name, bytes): gpu_name = gpu_name.decode()
                util = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_info = f"{gpu_name} ({util}%, {mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)"
            except Exception:
                pass

            has_audio_out = True
            try:
                from core.startup_manager import startup_manager
                has_audio_out = startup_manager.has_audio_output()
            except Exception:
                pass

            active_tasks = [asdict(t) for t in task_center.get_active_tasks()]
            recent_tasks = [asdict(t) for t in list(task_center._tasks.values())[-6:]]
            projs = [asdict(p) for p in project_manager._projects.values()]
            recent_events = [asdict(e) for e in timeline.get_recent(8)]
            unread_notifs = [asdict(n) for n in proactive_engine.get_unread_notifications()[-6:]]
            todays_reminders = [asdict(r) for r in proactive_engine.get_todays_reminders()]

            services = service_manager.get_all_services()
            degraded_services = [s for s in services.values() if not s.get("healthy") or not s.get("is_running")]

            recent_files = []
            if self._uploads_dir.exists():
                for f in sorted(self._uploads_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                    if f.is_file():
                        recent_files.append({"name": f.name, "size": f.stat().st_size})

            from core.screen_engine import screen_engine
            from core.privacy_manager import privacy_manager
            from core.app_adapters import app_registry

            fg_win = screen_engine.get_active_window()
            err_dlg = screen_engine.detect_error_dialog()
            vision_telemetry = {
                "active_window": {
                    "title": fg_win.title if fg_win else "Desktop",
                    "process_name": fg_win.process_name if fg_win else "explorer.exe",
                    "is_responsive": fg_win.is_responsive if fg_win else True,
                    "is_sensitive": fg_win.is_sensitive if fg_win else False,
                },
                "error_dialog": asdict(err_dlg),
                "privacy": privacy_manager.get_status(),
                "installed_apps_count": len(app_registry.list_installed_apps())
            }

            data = {
                "alex_state": "ONLINE",
                "owner": {
                    "name": OWNER_NAME,
                    "address": OWNER_ADDRESS,
                    "auth_level": security_manager.get_auth_level(),
                    "locked": security_manager.is_locked(),
                    "computer_control_allowed": security_manager.check_permission("computer_control")[0]
                },
                "vision": vision_telemetry,
                "audio": {
                    "input_ready": True,
                    "output_ready": has_audio_out,
                    "status": "Operational" if has_audio_out else "Audio Fallback",
                    "clap_wake": {
                        "enabled": clap_settings.enabled,
                        "sensitivity": clap_settings.sensitivity,
                        "chime": clap_settings.sound_enabled,
                    }
                },
                "network": {
                    "internet": True,
                    "gemini_api": bool(_get_gemini_key()),
                    "vpn": "Optional (Direct Connection)"
                },
                "hardware": {
                    "cpu_percent": cpu,
                    "ram_percent": vm.percent,
                    "ram_used_gb": round(vm.used / (1024**3), 1),
                    "ram_total_gb": round(vm.total / (1024**3), 1),
                    "disk_percent": disk_pct,
                    "disk_free_gb": disk_free,
                    "gpu": gpu_info
                },
                "tasks": {
                    "active": active_tasks,
                    "recent": recent_tasks,
                    "autonomy_level": task_center.get_autonomy_level()
                },
                "projects": {
                    "active_project": project_manager.get_active_project(),
                    "all": projs
                },
                "timeline": recent_events,
                "proactive": {
                    "dnd_mode": proactive_engine.settings.dnd_mode,
                    "quiet_hours_active": proactive_engine.is_quiet_hours(),
                    "unread_notifications": unread_notifs,
                    "reminders": todays_reminders
                },
                "recent_files": recent_files,
                "project_health": ProjectHealthInspector.inspect().to_dict(),
                "errors": [f"{s['name']}: {s['details']}" for s in degraded_services]
            }
            return JSONResponse({"ok": True, "overview": data})

        @app.post("/api/task-control")
        async def task_control_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            action = body.get("action", "").lower().strip()
            task_id = body.get("task_id", "").strip()
            from core.task_center import task_center
            if action == "pause":
                ok = task_center.pause_task(task_id)
                return JSONResponse({"ok": ok, "status": "PAUSED"})
            elif action == "resume":
                ok = task_center.resume_task(task_id)
                return JSONResponse({"ok": ok, "status": "RUNNING"})
            elif action == "cancel":
                ok = task_center.cancel_task(task_id)
                return JSONResponse({"ok": ok, "status": "CANCELLED"})
            elif action == "retry":
                retried = task_center.retry_task(task_id)
                return JSONResponse({"ok": bool(retried), "new_task_id": retried.task_id if retried else None})
            return JSONResponse({"error": "Invalid action"}, status_code=400)

        @app.post("/api/dnd")
        async def toggle_dnd_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.proactive_intelligence import proactive_engine
            res_str = proactive_engine.toggle_dnd()
            return JSONResponse({"ok": True, "dnd_mode": proactive_engine.settings.dnd_mode, "message": res_str})

        @app.post("/api/privacy-control")
        async def privacy_control_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            action = body.get("action", "").lower().strip()
            from core.privacy_manager import privacy_manager
            if action == "pause":
                msg = privacy_manager.pause_vision()
            elif action == "resume":
                msg = privacy_manager.resume_vision()
            elif action == "emergency_stop":
                msg = privacy_manager.emergency_stop()
            else:
                return JSONResponse({"error": "Invalid action"}, status_code=400)
            return JSONResponse({"ok": True, "message": msg, "privacy": privacy_manager.get_status()})

        # ── ALEX Phase 6: Knowledge Brain & Memory Management Endpoints ────────
        @app.get("/api/memory/stats")
        async def memory_stats_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            return JSONResponse({"ok": True, "stats": brain_store.get_brain_stats()})

        @app.get("/api/memory/entries")
        async def memory_entries_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            from dataclasses import asdict
            m_type = req.query_params.get("type")
            cat = req.query_params.get("category")
            proj = req.query_params.get("project")
            limit = int(req.query_params.get("limit", 100))
            mems = brain_store.list_memories(memory_type=m_type, category=cat, project_id=proj, limit=limit)
            return JSONResponse({"ok": True, "entries": [asdict(m) for m in mems]})

        @app.get("/api/memory/search")
        async def memory_search_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.memory_retriever import memory_retriever
            q = req.query_params.get("q", "")
            proj = req.query_params.get("project")
            res = memory_retriever.query(q, project_id=proj)
            return JSONResponse({
                "ok": True,
                "summary": res.summary_text,
                "found": res.found,
                "confidence": res.confidence,
                "source": res.source,
                "records": res.matched_records
            })

        @app.post("/api/memory/save")
        async def memory_save_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            content = body.get("content", "").strip()
            if not content:
                return JSONResponse({"error": "Content cannot be empty"}, status_code=400)
            from memory.brain_store import brain_store
            from dataclasses import asdict
            rec = brain_store.save_memory(
                content=content,
                category=body.get("category", "notes"),
                key=body.get("key"),
                project_id=body.get("project_id"),
                source="dashboard_ui"
            )
            return JSONResponse({"ok": True, "entry": asdict(rec)})

        @app.put("/api/memory/update/{mem_id}")
        async def memory_update_ep(mem_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            from memory.brain_store import brain_store
            from dataclasses import asdict
            rec = brain_store.get_memory(mem_id)
            if not rec:
                return JSONResponse({"error": "Memory not found"}, status_code=404)
            updated = brain_store.save_memory(
                content=body.get("content", rec.content),
                category=body.get("category", rec.category),
                key=body.get("key", rec.key),
                project_id=body.get("project_id", rec.project_id),
                source="dashboard_edit"
            )
            return JSONResponse({"ok": True, "entry": asdict(updated)})

        @app.delete("/api/memory/delete/{mem_id}")
        async def memory_delete_ep(mem_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            ok = brain_store.purge_memory(mem_id)
            return JSONResponse({"ok": ok})

        @app.post("/api/memory/clear-session")
        async def memory_clear_session_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            conn = brain_store._get_connection()
            with conn:
                conn.execute("DELETE FROM memories WHERE memory_type = 'session';")
                conn.execute("DELETE FROM memories_fts WHERE category = 'session_summary';")
            return JSONResponse({"ok": True, "message": "Session memory cleared."})

        @app.get("/api/memory/export")
        async def memory_export_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            fmt = req.query_params.get("format", "json")
            data = brain_store.export_memories(export_format=fmt)
            return JSONResponse({"ok": True, "format": fmt, "data": data})

        @app.post("/api/memory/backup")
        async def memory_backup_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            dest = BASE_DIR / "memory" / f"alex_brain_backup_{int(time.time())}.db"
            ok = brain_store.backup_database(dest)
            return JSONResponse({"ok": ok, "backup_path": str(dest)})

        @app.post("/api/memory/index-path")
        async def memory_index_path_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            target_path = body.get("path", "").strip()
            proj_id = body.get("project_id")
            from memory.document_indexer import document_indexer
            p = Path(target_path)
            if p.is_dir():
                res = document_indexer.index_directory(target_path, project_id=proj_id)
            else:
                res = document_indexer.index_file(target_path, project_id=proj_id)
            return JSONResponse({"ok": True, "result": res})

        @app.get("/api/memory/documents")
        async def memory_documents_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.brain_store import brain_store
            proj_id = req.query_params.get("project")
            docs = brain_store.list_documents(project_id=proj_id)
            return JSONResponse({"ok": True, "documents": docs})

        @app.get("/api/memory/conflicts")
        async def memory_conflicts_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from memory.conflict_resolver import conflict_resolver
            return JSONResponse({"ok": True, "conflicts": conflict_resolver.list_unresolved_conflicts()})

        @app.post("/api/memory/resolve-conflict")
        async def memory_resolve_conflict_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            cid = body.get("conflict_id", "")
            choice = body.get("choice", "ACCEPT_NEW")
            note = body.get("note", "")
            from memory.conflict_resolver import conflict_resolver
            ok = conflict_resolver.resolve_conflict(cid, choice=choice, owner_note=note)
            return JSONResponse({"ok": ok})

        # ── Phase 7: Skills Engine & Plugin Ecosystem Endpoints ───────────────
        @app.get("/api/skills/list")
        async def skills_list_ep(req: Request, category: str = "", status: str = "", search: str = ""):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from skills.engine import skills_engine
            items = skills_engine.list_skills(
                category=category or None,
                status=status or None,
                search_query=search or None
            )
            return JSONResponse({"ok": True, "skills": items, "count": len(items)})

        @app.post("/api/skills/{skill_id}/enable")
        async def skills_enable_ep(skill_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from skills.engine import skills_engine
            ok, msg = skills_engine.enable_skill(skill_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/skills/{skill_id}/disable")
        async def skills_disable_ep(skill_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from skills.engine import skills_engine
            ok, msg = skills_engine.disable_skill(skill_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.get("/api/skills/{skill_id}/health-check")
        async def skills_health_check_ep(skill_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from skills.engine import skills_engine
            ok, msg = skills_engine.check_skill_health(skill_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/skills/install")
        async def skills_install_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            code = body.get("code")
            plugin_name = body.get("plugin_name")
            source_path = body.get("source_path")
            from skills.plugin_installer import plugin_installer
            from skills.engine import skills_engine

            if code and plugin_name:
                ok, msg, diag = plugin_installer.install_plugin_code(code, plugin_name)
            elif source_path:
                ok, msg, diag = plugin_installer.install_plugin(source_path)
            else:
                return JSONResponse({"ok": False, "message": "Missing 'code' and 'plugin_name' or 'source_path'"}, status_code=400)

            if ok:
                skills_engine._discover_and_register_all()
            return JSONResponse({"ok": ok, "message": msg, "diagnostics": diag})

        @app.post("/api/skills/{skill_id}/rollback")
        async def skills_rollback_ep(skill_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from skills.plugin_installer import plugin_installer
            from skills.engine import skills_engine
            ok, msg = plugin_installer.rollback_plugin(skill_id)
            if ok:
                skills_engine._discover_and_register_all()
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/skills/execute")
        async def skills_execute_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            skill_id = body.get("skill_id", "")
            action = body.get("action")
            parameters = body.get("parameters", {})
            from skills.engine import skills_engine
            res = skills_engine.execute_skill(skill_id, action_name=action, parameters=parameters)
            return JSONResponse({"ok": res.verified, "result": res.to_dict()})

        # ── Phase 8: Multi-Step Workflow Orchestrator Endpoints ───────────────
        @app.get("/api/workflows/list")
        async def workflows_list_ep(req: Request, status: str = ""):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.orchestrator import workflow_orchestrator
            items = workflow_orchestrator.list_workflows(status=status or None)
            return JSONResponse({"ok": True, "workflows": items, "count": len(items)})

        @app.get("/api/workflows/{workflow_id}")
        async def workflow_detail_ep(workflow_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.orchestrator import workflow_orchestrator
            wf = workflow_orchestrator.get_workflow(workflow_id)
            if not wf:
                return JSONResponse({"ok": False, "error": "Workflow not found"}, status_code=404)
            return JSONResponse({"ok": True, "workflow": wf.to_dict()})

        @app.post("/api/workflows/submit")
        async def workflow_submit_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            request_text = body.get("request", "").strip()
            project_id = body.get("project_id")
            auto_start = body.get("auto_start", True)
            if not request_text:
                return JSONResponse({"ok": False, "error": "Request text is required"}, status_code=400)
            from workflow.orchestrator import workflow_orchestrator
            try:
                wf = workflow_orchestrator.submit_workflow(request_text, project_id=project_id, auto_start=auto_start)
                return JSONResponse({"ok": True, "workflow": wf.to_dict()})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        @app.post("/api/workflows/{workflow_id}/pause")
        async def workflow_pause_ep(workflow_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.orchestrator import workflow_orchestrator
            ok, msg = workflow_orchestrator.pause_workflow(workflow_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/workflows/{workflow_id}/resume")
        async def workflow_resume_ep(workflow_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.orchestrator import workflow_orchestrator
            ok, msg = workflow_orchestrator.resume_workflow(workflow_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/workflows/{workflow_id}/cancel")
        async def workflow_cancel_ep(workflow_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                body = {}
            reason = body.get("reason", "")
            from workflow.orchestrator import workflow_orchestrator
            ok, msg = workflow_orchestrator.cancel_workflow(workflow_id, reason=reason)
            return JSONResponse({"ok": ok, "message": msg})

        @app.post("/api/workflows/{workflow_id}/retry-task")
        async def workflow_retry_task_ep(workflow_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            task_id = body.get("task_id", "")
            from workflow.orchestrator import workflow_orchestrator
            ok, msg = workflow_orchestrator.retry_task(workflow_id, task_id)
            return JSONResponse({"ok": ok, "message": msg})

        @app.get("/api/workflows/approvals/pending")
        async def workflow_approvals_pending_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.approvals import approval_manager
            items = [a.to_dict() for a in approval_manager.list_pending()]
            return JSONResponse({"ok": True, "approvals": items})

        @app.post("/api/workflows/approvals/{approval_id}/decide")
        async def workflow_approval_decide_ep(approval_id: str, req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            decision = body.get("decision", "approve").lower()
            note = body.get("note", "")
            from workflow.orchestrator import workflow_orchestrator
            if decision == "approve":
                ok, msg = workflow_orchestrator.approve_task(approval_id, note=note)
            else:
                ok, msg = workflow_orchestrator.reject_task(approval_id, note=note)
            return JSONResponse({"ok": ok, "message": msg})

        @app.get("/api/workflows/artifacts/list")
        async def workflow_artifacts_list_ep(req: Request, workflow_id: str = ""):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from workflow.artifacts import artifact_manager
            items = [a.to_dict() for a in artifact_manager.list_artifacts(workflow_id or None)]
            return JSONResponse({"ok": True, "artifacts": items})

        # ── Dev Lab (Phase 9) Endpoints ─────────────────────────────────────
        _devlab_orchestrators = {}

        def _get_devlab(proj_path: str = ""):
            target = proj_path or str(BASE_DIR)
            if target not in _devlab_orchestrators:
                from dev_lab.orchestrator import DebugLabOrchestrator
                _devlab_orchestrators[target] = DebugLabOrchestrator(target)
            return _devlab_orchestrators[target]

        @app.get("/api/devlab/projects")
        async def devlab_projects_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.project_manager import ProjectManager
            pm = ProjectManager.get_instance()
            projs = [p.name for p in pm.get_all_projects()]
            if not projs:
                projs = [BASE_DIR.name]
            return JSONResponse({"ok": True, "projects": projs, "base_dir": str(BASE_DIR)})

        @app.post("/api/devlab/scan")
        async def devlab_scan_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json() if req.headers.get("content-type") == "application/json" else {}
            proj = body.get("project_path", str(BASE_DIR))
            orch = _get_devlab(proj)
            summary, findings = orch.inspect_and_scan()
            return JSONResponse({
                "ok": True,
                "summary": summary.to_dict(),
                "findings": [f.to_dict() for f in findings],
                "findings_count": len(findings),
            })

        @app.get("/api/devlab/findings")
        async def devlab_findings_ep(req: Request, status: str = "", project_path: str = ""):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            orch = _get_devlab(project_path)
            findings = orch.get_findings(status if status else None)
            return JSONResponse({"ok": True, "findings": [f.to_dict() for f in findings]})

        @app.post("/api/devlab/reproduce")
        async def devlab_reproduce_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            finding_id = body.get("finding_id", "")
            proj = body.get("project_path", str(BASE_DIR))
            orch = _get_devlab(proj)
            res = orch.run_reproduction(finding_id)
            return JSONResponse({"ok": True, "result": res.to_dict()})

        @app.post("/api/devlab/cycle")
        async def devlab_cycle_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            finding_id = body.get("finding_id", "")
            proj = body.get("project_path", str(BASE_DIR))
            orch = _get_devlab(proj)
            res = orch.execute_debugging_cycle(finding_id)
            return JSONResponse({"ok": True, "result": res})

        @app.post("/api/devlab/rollback")
        async def devlab_rollback_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            finding_id = body.get("finding_id", "")
            ckpt_id = body.get("checkpoint_id", "")
            proj = body.get("project_path", str(BASE_DIR))
            orch = _get_devlab(proj)
            res = orch.rollback_finding(finding_id, ckpt_id)
            return JSONResponse({"ok": True, "result": res})

        @app.get("/api/devlab/env-doctor")
        async def devlab_env_doctor_ep(req: Request, project_path: str = ""):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from dev_lab.env_doctor import EnvironmentDoctor
            doc = EnvironmentDoctor(project_path or str(BASE_DIR))
            rep = doc.diagnose()
            return JSONResponse({"ok": True, "report": rep.to_dict()})

        @app.get("/api/devlab/self-diag")
        async def devlab_self_diag_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from dev_lab.self_diagnostics import AlexSelfDiagnostics
            diag = AlexSelfDiagnostics(str(BASE_DIR))
            rep = diag.run_self_audit()
            return JSONResponse({"ok": True, "report": rep.to_dict()})

        # ── Multimodal Creation Studio (Phase 10) Endpoints ─────────────────
        @app.get("/api/creation/status")
        async def creation_status_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from creation_studio import creation_orchestrator
            caps = creation_orchestrator.get_tool_capabilities()
            return JSONResponse({"ok": True, "capabilities": caps.to_dict()})

        @app.get("/api/creation/templates")
        async def creation_templates_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from creation_studio import creation_orchestrator
            templates = [t.to_dict() for t in creation_orchestrator.list_templates()]
            return JSONResponse({"ok": True, "templates": templates})

        @app.get("/api/creation/tasks")
        async def creation_tasks_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from creation_studio import creation_orchestrator
            tasks = [t.to_dict() for t in creation_orchestrator._task_history.values()]
            return JSONResponse({"ok": True, "tasks": tasks})

        @app.post("/api/creation/create")
        async def creation_create_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            prompt = body.get("prompt", "").strip()
            if not prompt:
                return JSONResponse({"error": "Prompt cannot be empty."}, status_code=400)
            from creation_studio import creation_orchestrator, AssetType, OutputFormat
            asset_type_str = body.get("asset_type")
            target_fmt_str = body.get("target_format")
            input_files = body.get("input_files", [])
            project_name = body.get("project_name")
            template_name = body.get("template_name")

            atype = AssetType(asset_type_str) if asset_type_str else None
            tfmt = OutputFormat(target_fmt_str) if target_fmt_str else None

            task = creation_orchestrator.execute_creation_request(
                prompt=prompt,
                asset_type=atype,
                target_format=tfmt,
                input_files=input_files,
                project_name=project_name,
                template_name=template_name,
            )
            return JSONResponse({"ok": task.status.value == "COMPLETED", "task": task.to_dict()})



        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            # Auth via query param — browser <a download> can't send custom headers
            tok = token.strip()
            if not tok or tok not in self._tokens:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        enc = data.get("enc", "")
                        t   = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        if t:
                            await self._command_queue.put(t)
                            if self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_alias(self) -> None:
        """Second HTTPS server on PORT+1 sharing the same app and in-memory state.
        Chrome HTTPS-upgrades any bare IP:PORT the user types, so this port also needs TLS.
        User types IP:8001 → Chrome tries https → self-signed cert warning → accept once → done."""
        ssl_key  = BASE_DIR / "config" / "certs" / "alex.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "alex.crt"
        if not (ssl_key.exists() and ssl_cert.exists()):
            ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
            ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)
        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT + 1, log_level="warning",
            ssl_keyfile=str(ssl_key), ssl_certfile=str(ssl_cert),
        )
        print(f"[Dashboard] Manual entry:  {self._ip}:{PORT + 1}  (type in browser, accept cert once)")
        try:
            server = uvicorn.Server(cfg)
            await server.serve()
        except BaseException as e:
            print(f"[Dashboard] Alias server on port {PORT + 1} stopped or port in use: {e}")

    async def serve(self) -> None:
        if not _DEPS_OK:
            print("[Dashboard] fastapi/uvicorn not installed — dashboard disabled.")
            print("[Dashboard] Run:  pip install fastapi 'uvicorn[standard]' cryptography")
            return

        # Firewall setup runs in a thread — uvicorn starts immediately,
        # no waiting for UAC dialogs or subprocess timeouts.
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)

        # Generate the TLS pair on first run so no private key ships in the repo.
        _ensure_certs()

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "alex.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "alex.crt"
        if not (ssl_key.exists() and ssl_cert.exists()):
            ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
            ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        if use_ssl:
            asyncio.create_task(self._serve_alias())

        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT, log_level="warning",
            **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)} if use_ssl else {}),
        )

        proto = "https" if use_ssl else "http"
        print(f"[Dashboard] {proto}://{self._ip}:{PORT}")
        print("[Dashboard] Press 'Remote Control' in ALEX UI to get the QR code.")
        try:
            server = uvicorn.Server(cfg)
            await server.serve()
        except BaseException as e:
            print(f"[Dashboard] Server on port {PORT} stopped or port in use: {e}")
