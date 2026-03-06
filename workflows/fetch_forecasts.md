# SOP: Fetch Forecasts

## Purpose
Obtain consensus temperature forecasts for each unique (city, date) pair found in markets.

## Steps

1. **Deduplicate** — Collect unique `(city_key, date)` pairs from market list.

2. **NWS fetch** (per city/date):
   - `GET https://api.weather.gov/points/{lat},{lon}` → get `forecastUrl`
   - `GET {forecastUrl}` → find daytime period matching target date → extract high temp
   - Retry once on HTTP 500. Return `None` on any other failure.
   - Required header: `User-Agent: kalshi-weather-bot (contact@example.com)`

3. **Open-Meteo fetch** (per city/date):
   - `GET https://api.open-meteo.com/v1/forecast?latitude=...&daily=temperature_2m_max&temperature_unit=fahrenheit&timezone={tz}&forecast_days=7`
   - Extract `temperature_2m_max` for target date. Return `None` on failure.

4. **Score confidence**:
   | Condition | Confidence |
   |-----------|-----------|
   | Both present, diff ≤ 2°F | 0.70 |
   | Both present, diff ≤ 3°F | 0.55 |
   | Both present, diff ≤ 4°F | 0.40 |
   | Both present, diff ≤ 5°F | 0.30 |
   | Both present, diff > 5°F | 0.00 |
   | One source only | (above score) − 0.15 |
   | Both missing | 0.00 |

5. **Return** — Dict keyed by `(city_key, date)`: `{"temp": float|None, "confidence": float}`

## Notes
- Consensus temp = average of both sources when both present; single source otherwise
- NWS may return Celsius — convert with `°F = °C × 9/5 + 32`
