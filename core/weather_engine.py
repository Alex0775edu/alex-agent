"""
core/weather_engine.py — Fast, Lightweight Weather Intelligence for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Features:
  1. Real-time temperature, condition, humidity, and location fetching.
  2. Sub-2s response timeout with safe offline fallback.
  3. Caches weather data for 45 minutes to prevent redundant network hits.
  4. Never invents weather data if unreachable.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
WEATHER_CACHE = CONFIG_DIR / "weather_cache.json"


@dataclass
class WeatherInfo:
    available: bool
    temperature_c: str = ""
    condition: str = ""
    location: str = ""
    feels_like_c: str = ""
    humidity: str = ""
    timestamp: float = 0.0


class WeatherEngine:
    _instance: Optional[WeatherEngine] = None

    @classmethod
    def get_instance(cls) -> WeatherEngine:
        if cls._instance is None:
            cls._instance = WeatherEngine()
        return cls._instance

    def get_weather(self, force_refresh: bool = False) -> WeatherInfo:
        now = time.time()
        # 1. Check cache (<45 min)
        if not force_refresh and WEATHER_CACHE.exists():
            try:
                data = json.loads(WEATHER_CACHE.read_text(encoding="utf-8"))
                if now - data.get("timestamp", 0) < 2700:
                    return WeatherInfo(**data)
            except Exception:
                pass

        # 2. Fetch live weather via wttr.in JSON format (no API key required)
        try:
            req = urllib.request.Request(
                "https://wttr.in/?format=j1",
                headers={"User-Agent": "curl/7.68.0"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cur = data["current_condition"][0]
                area = data["nearest_area"][0]["areaName"][0]["value"]
                temp = cur["temp_C"]
                feels = cur.get("FeelsLikeC", temp)
                desc = cur["weatherDesc"][0]["value"]
                humidity = cur.get("humidity", "")

                info = WeatherInfo(
                    available=True,
                    temperature_c=temp,
                    condition=desc,
                    location=area,
                    feels_like_c=feels,
                    humidity=humidity,
                    timestamp=now
                )

                # Persist cache
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                WEATHER_CACHE.write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")
                return info
        except Exception:
            pass

        # 3. Fallback to older cache if present
        if WEATHER_CACHE.exists():
            try:
                data = json.loads(WEATHER_CACHE.read_text(encoding="utf-8"))
                info = WeatherInfo(**data)
                return info
            except Exception:
                pass

        return WeatherInfo(available=False)

    def format_weather_summary(self, lang: str = "hinglish") -> str:
        w = self.get_weather()
        if not w.available:
            return "Weather information is currently unavailable."
        
        if lang in ("hindi", "hinglish"):
            return f"{w.location} mein temperature abhi {w.temperature_c}°C hai, aur weather {w.condition.lower()} hai."
        return f"Currently in {w.location}, it is {w.temperature_c}°C with {w.condition.lower()}."


weather_engine = WeatherEngine.get_instance()

