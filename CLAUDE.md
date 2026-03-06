# Kalshi Weather Arbitrage Bot

## Project
Automated Kalshi prediction market bot. Scans weather temperature markets, fetches NOAA/NWS + Open-Meteo forecasts, places limit orders on mispricings. No human in the loop after startup. Real money, production API.

## Stack
Python 3.9+ | requests | python-dotenv | cryptography

## Run
```
pip install -r requirements.txt
python main.py
```

## Env
- `KALSHI_KEY_ID` — Kalshi API Key ID
- `KALSHI_PRIVATE_KEY_PATH` — path to RSA .pem (default: `api_keys/private_key.pem`)

## Key Constraints
- ALL prices in cents (yes_price=15 means $0.15)
- Sign path WITHOUT query params before hashing
- Public market endpoints: no auth headers
- No asyncio, no SDK, no ML
- HARD_CEILING=20¢ is never overrideable
- MAX_EXPOSURE_CENTS checked per-signal before placement

## WAT Framework
See `WAT CLAUDE.md` for workflow reference.
See `workflows/` for SOPs.

## Extensibility
To add a market category: add series config in config.py, subclass MarketScanner + BaseStrategy, add to MARKET_TYPES. No changes to main.py/executor.py/logger_utils.py.
