import logging
from datetime import date, datetime
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

NWS_HEADERS = {
    "User-Agent": "kalshi-weather-bot (contact@example.com)",
    "Accept": "application/geo+json",
}


def fetch_nws(lat: float, lon: float, target_date: str) -> Optional[float]:
    """Fetch NWS high temp forecast for target_date (YYYY-MM-DD). Returns °F or None."""
    try:
        points_url = f"{config.NWS_API_BASE}/points/{lat},{lon}"
        resp = requests.get(points_url, headers=NWS_HEADERS, timeout=10)
        resp.raise_for_status()
        forecast_url = resp.json()["properties"]["forecast"]

        resp2 = requests.get(forecast_url, headers=NWS_HEADERS, timeout=10)
        if resp2.status_code == 500:
            # Retry once
            resp2 = requests.get(forecast_url, headers=NWS_HEADERS, timeout=10)
        if not resp2.ok:
            return None

        target = date.fromisoformat(target_date)
        for period in resp2.json()["properties"]["periods"]:
            if not period.get("isDaytime", True):
                continue
            start = period.get("startTime", "")
            if not start:
                continue
            period_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
            if period_date == target:
                temp = period.get("temperature")
                unit = period.get("temperatureUnit", "F")
                if temp is None:
                    return None
                if unit == "C":
                    return temp * 9 / 5 + 32
                return float(temp)
    except Exception as e:
        logger.warning(f"weather_fetcher: NWS failed ({lat},{lon} {target_date}): {e}")
    return None


def fetch_open_meteo(lat: float, lon: float, target_date: str, tz: str = "UTC") -> Optional[float]:
    """Fetch Open-Meteo high temp forecast for target_date (YYYY-MM-DD). Returns °F or None."""
    try:
        url = (
            f"{config.OPEN_METEO_BASE}/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max"
            f"&temperature_unit=fahrenheit"
            f"&timezone={tz}"
            f"&forecast_days=7"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        dates = data["daily"]["time"]
        temps = data["daily"]["temperature_2m_max"]
        for d, t in zip(dates, temps):
            if d == target_date and t is not None:
                return float(t)
    except Exception as e:
        logger.warning(f"weather_fetcher: Open-Meteo failed ({lat},{lon} {target_date}): {e}")
    return None


def score_confidence(nws_temp: Optional[float], openmeteo_temp: Optional[float]) -> tuple[Optional[float], float]:
    """Return (consensus_temp, confidence) based on agreement between sources."""
    if nws_temp is not None and openmeteo_temp is not None:
        diff = abs(nws_temp - openmeteo_temp)
        consensus = (nws_temp + openmeteo_temp) / 2
        if diff <= 2:
            return consensus, 0.70
        elif diff <= 3:
            return consensus, 0.55
        elif diff <= 4:
            return consensus, 0.40
        elif diff <= 5:
            return consensus, 0.30
        else:
            return consensus, 0.00
    elif nws_temp is not None:
        return nws_temp, 0.70 - 0.15  # 0.55 — one source only
    elif openmeteo_temp is not None:
        return openmeteo_temp, 0.70 - 0.15
    else:
        return None, 0.00


def fetch_forecasts(markets: list[dict]) -> dict:
    """Fetch forecasts for all unique (city_key, date) pairs in markets.

    Returns dict keyed by (city_key, date): {"temp": float, "confidence": float}
    """
    unique = set()
    for m in markets:
        unique.add((m["city_key"], m["date"]))

    results = {}
    for city_key, target_date in unique:
        city = config.CITY_CONFIG.get(city_key)
        if city is None:
            logger.warning(f"weather_fetcher: no config for city {city_key}")
            results[(city_key, target_date)] = {"temp": None, "confidence": 0.00}
            continue

        lat, lon, tz = city["lat"], city["lon"], city["tz"]
        nws = fetch_nws(lat, lon, target_date)
        om = fetch_open_meteo(lat, lon, target_date, tz)
        temp, conf = score_confidence(nws, om)
        results[(city_key, target_date)] = {"temp": temp, "confidence": conf}
        logger.info(
            f"weather_fetcher: {city_key} {target_date} "
            f"NWS={nws} OM={om} consensus={temp:.1f if temp else 'N/A'} conf={conf:.2f}"
        )

    return results
