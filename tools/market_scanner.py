import json
import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional

import config
from tools.kalshi_auth import public_get

logger = logging.getLogger(__name__)


class MarketScanner:
    """Base class for market scanners. Subclass per market category."""

    def scan(self) -> list[dict]:
        raise NotImplementedError


class WeatherMarketScanner(MarketScanner):
    def scan(self) -> list[dict]:
        markets = []
        for city_key, series_ticker in config.WEATHER_SERIES.items():
            try:
                path = f"/markets?series_ticker={series_ticker}&status=open"
                data = public_get(config.KALSHI_API_BASE, path)
                raw_markets = data.get("markets", [])
                for m in raw_markets:
                    parsed = self._parse_market(m, city_key)
                    if parsed is None:
                        continue
                    if parsed["hours_to_resolution"] > config.MAX_FORECAST_HOURS:
                        continue
                    markets.append(parsed)
            except Exception as e:
                logger.warning(f"market_scanner: failed for series {series_ticker}: {e}")

        self._maybe_discover_series()
        return markets

    def _parse_market(self, m: dict, city_key: str) -> Optional[dict]:
        ticker = m.get("ticker", "")
        subtitle = m.get("subtitle") or ""
        title = m.get("title") or ""
        # Use yes_ask as the price we'd pay when buying
        yes_price = m.get("yes_ask") or m.get("last_price") or 0
        volume = m.get("volume", 0)
        close_time = m.get("close_time") or m.get("expiration_time", "")

        # Try subtitle first, fall back to title for empty subtitles (DAL, LA)
        text_to_parse = subtitle if subtitle.strip() else title
        bucket = self._parse_subtitle(text_to_parse)
        if bucket is None:
            return None

        date = self._parse_event_ticker(ticker)
        if date is None:
            return None

        hours = self._hours_until(close_time)

        return {
            "ticker": ticker,
            "city_key": city_key,
            "date": date,
            "subtitle": text_to_parse,
            "yes_price": int(yes_price),
            "volume": volume,
            "close_time": close_time,
            "hours_to_resolution": hours,
            "bucket_low": bucket[0],
            "bucket_high": bucket[1],
        }

    def _parse_subtitle(self, subtitle: str) -> Optional[tuple[int, int]]:
        """Parse temperature bucket from subtitle or title text.

        Handles:
          '47° to 48°'       → (47, 48)
          '49° or above'     → (49, 9999)
          '40° or below'     → (-9999, 40)
          'Above 80°'        → (80, 9999)
          'Below 32°'        → (-9999, 32)
          '>48° on Mar 6'    → (48, 9999)  (from title)
        """
        # Range: '47° to 48°'
        match = re.search(r"(\d+)[°\s]*\s+to\s+(\d+)", subtitle, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))

        # '49° or above' — number first
        match = re.search(r"(\d+)[°\s]*\s+or\s+above", subtitle, re.IGNORECASE)
        if match:
            return int(match.group(1)), 9999

        # '40° or below' — number first
        match = re.search(r"(\d+)[°\s]*\s+or\s+below", subtitle, re.IGNORECASE)
        if match:
            return -9999, int(match.group(1))

        # 'Above 80°' — word first
        match = re.search(r"above\s+(\d+)", subtitle, re.IGNORECASE)
        if match:
            return int(match.group(1)), 9999

        # 'Below 32°' — word first
        match = re.search(r"below\s+(\d+)", subtitle, re.IGNORECASE)
        if match:
            return -9999, int(match.group(1))

        # '>48°' from title like 'Will the high temp be >48° on ...'
        match = re.search(r">(\d+)[°\s]", subtitle, re.IGNORECASE)
        if match:
            return int(match.group(1)), 9999

        return None

    def _parse_event_ticker(self, ticker: str) -> Optional[str]:
        """Extract date string from ticker like 'KXHIGHNY-26MAR07-T48' → '2026-03-07'."""
        match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(?:-|$)", ticker)
        if not match:
            return None
        yy, mon_str, dd = match.group(1), match.group(2), match.group(3)
        months = {
            "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
            "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
            "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
        }
        month_num = months.get(mon_str.upper())
        if month_num is None:
            return None
        return f"20{yy}-{month_num}-{dd}"

    def _hours_until(self, close_time_str: str) -> float:
        if not close_time_str:
            return 9999.0
        try:
            # Handle ISO 8601 with Z or offset
            ct = close_time_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ct)
            now = datetime.now(timezone.utc)
            delta = dt - now
            return max(delta.total_seconds() / 3600, 0.0)
        except Exception:
            return 9999.0

    def _maybe_discover_series(self):
        """On first run, discover all Climate and Weather series from open markets."""
        path = os.path.join(config.TMP_DIR, "discovered_series.json")
        if os.path.exists(path):
            return
        try:
            data = public_get(config.KALSHI_API_BASE, "/markets?status=open&limit=200")
            weather_series = set()
            for m in data.get("markets", []):
                category = m.get("category") or ""
                series = m.get("series_ticker") or ""
                if "weather" in category.lower() or "climate" in category.lower():
                    if series:
                        weather_series.add(series)
            os.makedirs(config.TMP_DIR, exist_ok=True)
            with open(path, "w") as f:
                json.dump(sorted(weather_series), f, indent=2)
            logger.info(f"market_scanner: discovered {len(weather_series)} weather series")
        except Exception as e:
            logger.warning(f"market_scanner: discovery failed: {e}")


def scan_all() -> list[dict]:
    """Instantiate and run scanners for all configured market types."""
    markets = []
    for market_type in config.MARKET_TYPES:
        if market_type == "weather":
            scanner = WeatherMarketScanner()
        else:
            logger.warning(f"market_scanner: unknown market type '{market_type}', skipping")
            continue
        markets.extend(scanner.scan())
    return markets
