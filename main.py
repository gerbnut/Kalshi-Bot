import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

import config
import tools.alerting as alerting
import tools.executor as executor
import tools.market_scanner as market_scanner
import tools.pnl_tracker as pnl_tracker
import tools.reddit_research as reddit_research
import tools.strategy as strategy
import tools.weather_fetcher as weather_fetcher
from tools.kalshi_auth import KalshiClient
from tools.logger_utils import ScanLogger
from tools.utils import cents_to_dollars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

_SERIES_TO_CITY = {v: k for k, v in config.WEATHER_SERIES.items()}
_DATE_MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def _parse_held_position(ticker: str):
    """Parse a Kalshi position ticker into (city_key, date_str), or None if not a weather market."""
    parts = ticker.split("-")
    if len(parts) < 2:
        return None
    city_key = _SERIES_TO_CITY.get(parts[0])
    if not city_key:
        return None
    match = re.match(r"(\d{2})([A-Z]{3})(\d{2})$", parts[1])
    if not match:
        return None
    month_num = _DATE_MONTHS.get(match.group(2))
    if not month_num:
        return None
    return city_key, f"20{match.group(1)}-{month_num}-{match.group(3)}"


def _get_held_sets(client) -> tuple[set, set]:
    """Fetch open positions and return (held_tickers, held_city_dates).
    Returns empty sets on failure so trading is never blocked by an API error.
    """
    try:
        pos_data = client.get_positions()
        pos_list = pos_data.get("market_positions", []) or pos_data.get("positions", [])
        held_tickers = set()
        held_city_dates = set()
        for p in pos_list:
            qty = p.get("position", p.get("quantity", 0)) or 0
            if qty <= 0:
                continue
            ticker = p.get("ticker", "")
            held_tickers.add(ticker)
            parsed = _parse_held_position(ticker)
            if parsed:
                held_city_dates.add(parsed)
        if held_tickers:
            logger.info(f"main: holding {len(held_tickers)} position(s): {', '.join(sorted(held_tickers))}")
        return held_tickers, held_city_dates
    except Exception as e:
        logger.warning(f"main: get_positions failed, skipping held-position filter: {e}")
        return set(), set()


def main():
    # Step 1: Load and validate env
    load_dotenv()
    key_id = os.environ.get("KALSHI_KEY_ID", "").strip()
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()

    if not key_id or key_id == "your-key-id-here":
        print("ERROR: KALSHI_KEY_ID not set in .env")
        sys.exit(1)
    if not key_path:
        print("ERROR: KALSHI_PRIVATE_KEY_PATH not set in .env")
        sys.exit(1)
    if not os.path.exists(key_path):
        print(f"ERROR: Private key not found at {key_path}")
        print("       Generate a new key pair on kalshi.com → Account → API Keys")
        print(f"       Then place the .pem file at: {key_path}")
        sys.exit(1)

    # Step 2: Build client
    client = KalshiClient(config.KALSHI_API_BASE, key_id, key_path)

    # Step 3: Startup check
    initial_balance = executor.startup_check(client)

    # Step 4: Config summary
    config_summary = (
        f"ENTRY={config.ENTRY_THRESHOLD}¢  CEILING={config.HARD_CEILING}¢  "
        f"EDGE={config.MIN_EDGE}  CONF={config.MIN_CONFIDENCE}  "
        f"TRADE={config.MAX_TRADE_PCT*100:.0f}%  EXP={config.MAX_EXPOSURE_PCT*100:.0f}%  "
        f"INTERVAL={config.SCAN_INTERVAL_SECONDS}s"
    )
    print(f"  Config:")
    print(f"    ENTRY_THRESHOLD={config.ENTRY_THRESHOLD}¢  HARD_CEILING={config.HARD_CEILING}¢")
    print(f"    MIN_EDGE={config.MIN_EDGE}  MIN_CONFIDENCE={config.MIN_CONFIDENCE}")
    print(f"    MAX_EXPOSURE={cents_to_dollars(config.MAX_EXPOSURE_CENTS)}")
    print(f"    MAX_TRADE={cents_to_dollars(config.MAX_TRADE_CENTS)}  MAX_TRADES_PER_RUN={config.MAX_TRADES_PER_RUN}")
    print(f"    MAX_FORECAST_HOURS={config.MAX_FORECAST_HOURS}h  SCAN_INTERVAL={config.SCAN_INTERVAL_SECONDS}s")
    print(f"    Cities: {', '.join(config.WEATHER_SERIES.keys())}")
    print()

    # Step 5: P&L update on startup
    try:
        pnl_stats = pnl_tracker.update_pnl()
        print(pnl_tracker.format_summary(pnl_stats))
        print()
    except Exception as e:
        logger.warning(f"pnl_tracker startup: {e}")
        pnl_stats = {"total_resolved": 0, "total_unresolved": 0, "wins": 0, "losses": 0,
                     "win_rate": 0.0, "total_cost_cents": 0, "total_pnl_cents": 0, "roi_pct": 0.0, "newly_resolved": []}

    # Step 6: Startup alert
    alerting.alert_startup(initial_balance, config_summary)

    scan_logger = ScanLogger()
    scan_count = 0
    session_orders = 0
    current_balance = initial_balance
    last_summary_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        while True:
            scan_count += 1
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Daily summary alert when the day rolls over
            if today != last_summary_day:
                try:
                    bal = client.get_balance()
                    current_balance = bal.get("balance", initial_balance)
                except Exception:
                    current_balance = initial_balance
                try:
                    pos_data = client.get_positions()
                    positions = pos_data.get("market_positions", []) or pos_data.get("positions", [])
                except Exception:
                    positions = None
                alerting.alert_daily_summary(scan_count, session_orders, current_balance, pnl_stats, positions)
                last_summary_day = today

            # Daily Reddit research (runs once per day, non-blocking on failure)
            reddit_research.research_today_if_needed()

            # Fetch fresh balance and held positions at the start of each scan
            scan_balance = current_balance
            try:
                bal = client.get_balance()
                scan_balance = bal.get("balance", current_balance)
                current_balance = scan_balance
            except Exception:
                pass
            held_tickers, held_city_dates = _get_held_sets(client)
            print(f"  Balance: {cents_to_dollars(scan_balance)}  |  Held: {len(held_tickers)}")

            # Scan → Forecast → Evaluate
            try:
                markets = market_scanner.scan_all()
            except Exception as e:
                scan_logger.log_error("scan_all", e)
                markets = []

            try:
                forecasts = weather_fetcher.fetch_forecasts(markets)
            except Exception as e:
                scan_logger.log_error("fetch_forecasts", e)
                forecasts = {}

            # Compute account-relative position limits (hard caps — balance check is additional)
            effective_trade = max(config.MAX_TRADE_CENTS, int(scan_balance * config.MAX_TRADE_PCT))
            effective_exposure = max(config.MAX_EXPOSURE_CENTS, int(scan_balance * config.MAX_EXPOSURE_PCT))

            try:
                signals, skipped_details = strategy.evaluate(
                    markets, forecasts, effective_trade, effective_exposure,
                    available_balance_cents=scan_balance,
                    held_tickers=held_tickers,
                    held_city_dates=held_city_dates,
                )
            except Exception as e:
                scan_logger.log_error("strategy.evaluate", e)
                signals, skipped_details = [], []

            # Execute — pass balance so executor tracks spend in real time
            executed, remaining_balance = executor.execute_signals(client, signals, scan_balance)

            # Alert on each trade result
            for e in executed:
                if e.get("status") == "error":
                    alerting.alert_trade_failed(e["ticker"], e.get("error", "unknown"))
                else:
                    alerting.alert_trade_placed(
                        e["ticker"], e["count"], e["limit_price"],
                        e.get("order_id"), e.get("status"),
                        balance_after=e.get("balance_after"),
                    )

            successful = [e for e in executed if e.get("status") != "error"]
            session_orders += len(successful)

            # Exposure = sum of executed trade costs
            exposure_cents = sum(e["count"] * e["limit_price"] for e in successful)

            # Post-scan balance summary
            if successful:
                remaining_str = cents_to_dollars(remaining_balance) if remaining_balance is not None else "unknown"
                print(f"  Scan summary: started={cents_to_dollars(scan_balance)}  "
                      f"allocated={cents_to_dollars(exposure_cents)}  remaining={remaining_str}")

            # Update current_balance from API (ground truth for next scan)
            try:
                bal = client.get_balance()
                current_balance = bal.get("balance", current_balance)
            except Exception:
                pass

            # Log scan
            scan_logger.log_scan(
                scan_num=scan_count,
                markets=markets,
                signals=signals,
                executed=executed,
                skipped_details=skipped_details,
                balance_cents=current_balance,
                exposure_cents=exposure_cents,
            )

            # P&L update every scan (tries to resolve newly settled markets)
            try:
                pnl_stats = pnl_tracker.update_pnl()
                if pnl_stats["newly_resolved"]:
                    print(pnl_tracker.format_summary(pnl_stats))
            except Exception as e:
                logger.warning(f"pnl_tracker: {e}")

            time.sleep(config.SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print(f"\n{'='*60}")
        print(f"  SHUTDOWN")
        print(f"  Scans completed: {scan_count}")
        print(f"  Orders placed:   {session_orders}")
        executor.session_summary(client, initial_balance)
        try:
            final_pnl = pnl_tracker.update_pnl()
            print(pnl_tracker.format_summary(final_pnl))
            bal = client.get_balance()
            alerting.alert_daily_summary(scan_count, session_orders, bal.get("balance", 0), final_pnl)
        except Exception:
            pass
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
