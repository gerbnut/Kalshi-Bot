# SOP: Scan Markets

## Purpose
Discover open Kalshi weather temperature markets for configured cities.

## Steps

1. **Iterate series** — For each city in `config.WEATHER_SERIES`, call:
   `GET /markets?series_ticker={ticker}&status=open`

2. **Parse each market** — Extract:
   - `ticker` (e.g., `HIGHNY-26MAR07`)
   - `subtitle` → parse temperature bucket (e.g., `43° to 44°` → `(43, 44)`)
   - `yes_bid` or `last_price` → `yes_price` (cents)
   - `close_time` → `hours_to_resolution`

3. **Filter** — Skip markets where `hours_to_resolution > MAX_FORECAST_HOURS` (72h).

4. **Discovery (first run only)** — Call `/markets?status=open&limit=200`, filter for
   "Climate and Weather" category, save series tickers to `.tmp/discovered_series.json`.

5. **Error handling** — On 404 or empty response: log warning and skip. Never raise.

## Output
List of market dicts with: `ticker`, `city_key`, `date`, `yes_price`, `bucket_low`,
`bucket_high`, `hours_to_resolution`, `close_time`.

## Notes
- All endpoints are public (no auth headers)
- `yes_price` is always in cents
