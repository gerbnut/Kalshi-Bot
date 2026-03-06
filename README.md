# Kalshi Bot                                                                                                                                                                                    
                                                                                                                                                                                                  
  Automated prediction market bot for [Kalshi](https://kalshi.com) weather temperature markets. Scans open markets, fetches NOAA/NWS + Open-Meteo forecasts, and places limit orders on           
  mispricings. Runs continuously with no human in the loop after startup.                                                                                                                         
                                                                                                                                                                                                  
  ---                                                                                                                                                                                             
                                                                                                                                                                                                  
  ## How It Works

  1. **Scan** — Fetches open temperature markets for 5 US cities (NY, CHI, DAL, MIA, LA)
  2. **Forecast** — Pulls NWS and Open-Meteo forecasts, computes consensus temp + confidence
  3. **Evaluate** — Scores each market for edge (confidence − market price); skips anything above the hard ceiling
  4. **Execute** — Places limit orders on signals that pass all filters
  5. **Alert** — Sends trade notifications and daily summaries via Discord

  ---

  ## Setup

  ```bash
  git clone https://github.com/gerbnut/Kalshi-Bot.git
  cd Kalshi-Bot
  pip install -r requirements.txt

  Create a .env file:

  KALSHI_KEY_ID=your-key-id
  KALSHI_PRIVATE_KEY_PATH=api_keys/private_key.pem
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # optional

  Place your RSA private key at the path specified above (generate at kalshi.com → Account → API Keys).

  python main.py

  ---
  Strategy

  ┌──────────────────┬───────┬───────────────────────────────────────────┐
  │    Parameter     │ Value │                Description                │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ ENTRY_THRESHOLD  │ 20¢   │ Skip markets priced above this            │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ HARD_CEILING     │ 20¢   │ Absolute max — never overrideable         │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ MIN_CONFIDENCE   │ 0.30  │ Min forecast agreement to trade           │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ MIN_EDGE         │ 0.05  │ Min (confidence − price) to signal        │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ MAX_TRADE_PCT    │ 5%    │ Max per-trade size (% of balance)         │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ MAX_EXPOSURE_PCT │ 20%   │ Max total session exposure (% of balance) │
  ├──────────────────┼───────┼───────────────────────────────────────────┤
  │ SCAN_INTERVAL    │ 300s  │ Time between scans                        │
  └──────────────────┴───────┴───────────────────────────────────────────┘

  Position sizing scales with account balance. Absolute floors apply if balance fetch fails ($5/trade, $50/session).

  ---
  Alerts

  Configure in .env:

  - DISCORD_WEBHOOK_URL — receives [BOT STARTED], [TRADE PLACED], [SCAN #1 SUMMARY], [DAILY SUMMARY]
  - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID — optional Telegram support

  ---
  Project Structure

  main.py               # Entry point + main loop
  config.py             # All constants and thresholds
  tools/
    strategy.py         # Signal scoring and filtering
    market_scanner.py   # Kalshi market fetcher
    weather_fetcher.py  # NWS + Open-Meteo forecast fetcher
    executor.py         # Order placement
    alerting.py         # Discord / Telegram notifications
    logger_utils.py     # JSON scan logs
    pnl_tracker.py      # P&L tracking
    kalshi_auth.py      # RSA auth client
  workflows/            # SOPs for each pipeline stage
  logs/                 # JSON trade logs (gitignored)

  ---
  Extending

  To add a new market category (e.g. crypto):
  1. Add series config in config.py
  2. Subclass MarketScanner and BaseStrategy
  3. Add to MARKET_TYPES

  No changes needed to main.py, executor.py, or alerting.py.

  ---
  Disclaimer

  This bot trades real money on live markets. Use at your own risk. Past edge does not guarantee future profit.
