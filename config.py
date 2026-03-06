import os

# Kalshi API
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Strategy constants
ENTRY_THRESHOLD = 20       # cents — skip if yes_price > this
HARD_CEILING = 20          # cents — hard block, never overrideable
MIN_EDGE = 0.05            # minimum (confidence - yes_price/100)
MIN_CONFIDENCE = 0.30      # minimum forecast confidence to trade
MAX_EXPOSURE_CENTS = 5000  # $50.00 absolute floor (used if balance fetch fails)
MAX_TRADE_CENTS = 500      # $5.00 absolute floor (used if balance fetch fails)
MAX_TRADE_PCT = 0.05       # 5% of account balance per trade
MAX_EXPOSURE_PCT = 0.20    # 20% of account balance total per session
MAX_TRADES_PER_RUN = 5     # cap signals per scan cycle
MAX_FORECAST_HOURS = 72    # skip markets resolving beyond this

# Bot timing
SCAN_INTERVAL_SECONDS = 300  # 5 minutes between scans

# Weather series: city_key -> Kalshi series ticker
WEATHER_SERIES = {
    "NY":  "KXHIGHNY",
    "CHI": "KXHIGHCHI",
    "DAL": "KXHIGHTDAL",
    "MIA": "KXHIGHMIA",
    "LA":  "KXHIGHLAX",
}

# City coordinates and timezones for weather APIs
CITY_CONFIG = {
    "NY":  {"lat": 40.7128, "lon": -74.0060, "tz": "America/New_York"},
    "CHI": {"lat": 41.8781, "lon": -87.6298, "tz": "America/Chicago"},
    "DAL": {"lat": 32.7767, "lon": -96.7970, "tz": "America/Chicago"},
    "MIA": {"lat": 25.7617, "lon": -80.1918, "tz": "America/New_York"},
    "LA":  {"lat": 34.0522, "lon": -118.2437, "tz": "America/Los_Angeles"},
}

# Market categories to scan (extensible)
MARKET_TYPES = ["weather"]

# External API base URLs
NWS_API_BASE = "https://api.weather.gov"
OPEN_METEO_BASE = "https://api.open-meteo.com"

# Paths
LOG_DIR = "logs"
TMP_DIR = ".tmp"
DISCOVERED_SERIES_PATH = ".tmp/discovered_series.json"
