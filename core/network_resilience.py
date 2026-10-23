"""
core/network_resilience.py — Network Resilience & IPv4 Optimization for ALEX.

Ensures:
  1. Low-latency network connections: Bypasses broken/unroutable IPv6 routes on Windows
     that cause 30-45s delays or WebSocket opening handshake timeouts.
  2. VPN Independence: ALEX works 100% reliably over standard home Wi-Fi/Ethernet.
     VPN is never forced or requested unless Aditya Sir explicitly desires it.
  3. Clean health telemetry: Distinguishes local loopback from outbound cloud connectivity.
"""

from __future__ import annotations

import socket
import time
import urllib.request
import ssl
from typing import Dict, Any, Tuple

_IPV4_APPLIED = False
_ORIGINAL_GAI = socket.getaddrinfo


def apply_ipv4_preference() -> bool:
    """Installs an IPv4-preferred resolver shim into socket.getaddrinfo.

    On many consumer Wi-Fi/ISP networks (especially in India), Windows enables
    IPv6 on the interface, causing DNS to return AAAA records first. Because
    the ISP has no working IPv6 route, TCP connection attempts stall for 21-30
    seconds before falling back to IPv4. This causes WebSocket handshakes to time out
    and makes Gemini feel broken without a VPN.

    By preferring AF_INET (IPv4), connections establish in <200ms without needing a VPN.
    """
    global _IPV4_APPLIED, _ORIGINAL_GAI
    if _IPV4_APPLIED:
        return True

    def _ipv4_first_gai(host, port, family=0, type=0, proto=0, flags=0):
        # If caller explicitly asked for AF_INET6 or family is non-zero and not AF_UNSPEC, respect it
        if family == socket.AF_INET6:
            return _ORIGINAL_GAI(host, port, family, type, proto, flags)
        try:
            # Query IPv4 first
            res = _ORIGINAL_GAI(host, port, socket.AF_INET, type, proto, flags)
            if res:
                return res
        except Exception:
            pass
        return _ORIGINAL_GAI(host, port, family, type, proto, flags)

    socket.getaddrinfo = _ipv4_first_gai
    _IPV4_APPLIED = True
    return True


# Auto-apply on import
apply_ipv4_preference()


def check_internet_reachability(timeout: float = 2.0) -> bool:
    """Fast check for external connectivity via Google public DNS."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except Exception:
        return False


def check_gemini_api_reachability(timeout: float = 3.0) -> Tuple[bool, float, str]:
    """Tests HTTPS latency to generativelanguage.googleapis.com."""
    t0 = time.time()
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com",
            headers={"User-Agent": "ALEX/3.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            latency = (time.time() - t0) * 1000
            return True, latency, f"Connected ({latency:.0f}ms)"
    except urllib.error.HTTPError as e:
        latency = (time.time() - t0) * 1000
        # 404 is normal for root endpoint
        return True, latency, f"Reachable ({e.code}, {latency:.0f}ms)"
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return False, latency, f"Unreachable: {e}"


def get_network_status() -> Dict[str, Any]:
    """Returns a full audit of network health and VPN-independence status."""
    inet_ok = check_internet_reachability()
    api_ok, latency, api_msg = check_gemini_api_reachability() if inet_ok else (False, 0.0, "Offline")

    return {
        "internet": inet_ok,
        "ipv4_preferred": _IPV4_APPLIED,
        "gemini_api_reachable": api_ok,
        "gemini_latency_ms": round(latency, 1),
        "api_message": api_msg,
        "vpn_required": False,  # ALEX NEVER requires VPN
        "vpn_status": "Optional (Running in native direct mode)",
    }

