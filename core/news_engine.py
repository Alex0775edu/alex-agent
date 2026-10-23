"""
core/news_engine.py — High-Performance Multi-Source News Intelligence Skill for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Features:
  1. Multi-source RSS news aggregation (Google News India, Tech, AI, World, Business).
  2. Local deduplication, filtering, and priority ranking.
  3. Category filtering and user preference customization.
  4. Concise 1-sentence summaries for speech (<30-90s audio safety).
  5. Fallback cache when offline or network drops.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CACHE_FILE = CONFIG_DIR / "news_cache.json"
PREFS_FILE = CONFIG_DIR / "news_preferences.json"

DEFAULT_CATEGORIES = ["India", "Technology", "AI", "Business", "World"]

RSS_FEEDS = {
    "India": "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    "Technology": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "AI": "https://news.google.com/rss/search?q=Artificial+Intelligence+when:24h&hl=en-IN&gl=IN&ceid=IN:en",
    "Business": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
    "World": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en"
}


@dataclass
class NewsItem:
    headline: str
    source: str
    category: str
    timestamp: str
    url: str
    summary: str


class NewsIntelligence:
    _instance: Optional[NewsIntelligence] = None

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> NewsIntelligence:
        if cls._instance is None:
            cls._instance = NewsIntelligence()
        return cls._instance

    def get_preferences(self) -> Dict[str, bool]:
        if PREFS_FILE.exists():
            try:
                return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {cat: True for cat in DEFAULT_CATEGORIES}

    def set_preference(self, category: str, enabled: bool) -> None:
        prefs = self.get_preferences()
        matched = False
        for c in DEFAULT_CATEGORIES:
            if c.lower() == category.lower():
                prefs[c] = enabled
                matched = True
        if not matched:
            prefs[category.title()] = enabled
        PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")

    def _fetch_category_rss(self, category: str, url: str, limit: int = 4) -> List[NewsItem]:
        items = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ALEX/3.0"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)
                for item in root.findall("./channel/item")[:limit]:
                    raw_title = (item.find("title").text or "").strip()
                    link = (item.find("link").text or "").strip()
                    pub_date = (item.find("pubDate").text or "").strip()

                    # Extract source if formatted as "Headline - Source"
                    source = "News Feed"
                    headline = raw_title
                    if " - " in raw_title:
                        parts = raw_title.rsplit(" - ", 1)
                        headline = parts[0].strip()
                        source = parts[1].strip()

                    # Concise clean summary
                    summary = f"{headline} (Reported by {source})"

                    items.append(NewsItem(
                        headline=headline,
                        source=source,
                        category=category,
                        timestamp=pub_date,
                        url=link,
                        summary=summary
                    ))
        except Exception:
            pass
        return items

    def fetch_top_news(self, force_refresh: bool = False, max_per_cat: int = 2) -> List[NewsItem]:
        """Fetch, filter, rank, and deduplicate top headlines across user-preferred categories."""
        # 1. Check recent cache (<30 min)
        now = time.time()
        if not force_refresh and CACHE_FILE.exists():
            try:
                cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                if now - cache_data.get("timestamp", 0) < 1800:
                    cached_items = [NewsItem(**it) for it in cache_data.get("items", [])]
                    if cached_items:
                        return cached_items
            except Exception:
                pass

        prefs = self.get_preferences()
        all_items: List[NewsItem] = []
        seen_headlines = set()

        for cat, feed_url in RSS_FEEDS.items():
            if not prefs.get(cat, True):
                continue
            cat_items = self._fetch_category_rss(cat, feed_url, limit=max_per_cat)
            for it in cat_items:
                clean_key = re.sub(r"[^a-zA-Z0-9]", "", it.headline.lower())[:40]
                if clean_key and clean_key not in seen_headlines:
                    seen_headlines.add(clean_key)
                    all_items.append(it)

        # 2. If online fetch succeeded, save cache
        if all_items:
            try:
                cache_payload = {
                    "timestamp": now,
                    "items": [asdict(it) for it in all_items]
                }
                CACHE_FILE.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")
            except Exception:
                pass
            return all_items

        # 3. Fallback to cached items even if older
        if CACHE_FILE.exists():
            try:
                cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                return [NewsItem(**it) for it in cache_data.get("items", [])]
            except Exception:
                pass

        return []

    def format_news_for_briefing(self, max_items: int = 4) -> str:
        """Formatted 1-sentence summaries suitable for speech (<45s audio safety)."""
        items = self.fetch_top_news()[:max_items]
        if not items:
            return "Current news updates are temporarily unavailable."

        lines = ["Today's important headlines:"]
        for it in items:
            lines.append(f"In {it.category}: {it.headline}.")
        return " ".join(lines)

    def format_news_table(self) -> str:
        """Structured text display for UI/Dashboard."""
        items = self.fetch_top_news()
        if not items:
            return "No news items available."

        lines = ["TODAY'S IMPORTANT NEWS", "-" * 42]
        by_cat: Dict[str, List[NewsItem]] = {}
        for it in items:
            by_cat.setdefault(it.category, []).append(it)

        for cat, cat_items in by_cat.items():
            lines.append(f"[{cat.upper()}]")
            for it in cat_items:
                lines.append(f"  • {it.headline} ({it.source})")
            lines.append("")
        return "\n".join(lines).strip()


news_intelligence = NewsIntelligence.get_instance()

