"""
P&L Tracker — resolves executed trades against Kalshi market outcomes.

Resolution logic:
  - Bought YES @ limit_price¢ per contract
  - If market resolves YES → revenue = count * 100¢
  - If market resolves NO  → revenue = 0
  - P&L = revenue - (count * limit_price)

Persistence: logs/pnl_resolved.json
  {"resolved": {ticker: {...}}, "unresolved": {ticker: {...}}}
"""
import json
import logging
import os
from datetime import datetime, timezone

import config
from tools.kalshi_auth import public_get
from tools.utils import cents_to_dollars

logger = logging.getLogger(__name__)

PNL_FILE = os.path.join(config.LOG_DIR, "pnl_resolved.json")


# ---------------------------------------------------------------------------
# Store I/O
# ---------------------------------------------------------------------------

def _load_store() -> dict:
    if os.path.exists(PNL_FILE):
        try:
            with open(PNL_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"resolved": {}, "unresolved": {}}


def _save_store(store: dict):
    os.makedirs(config.LOG_DIR, exist_ok=True)
    with open(PNL_FILE, "w") as f:
        json.dump(store, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Trade log ingestion
# ---------------------------------------------------------------------------

def _load_all_executed_trades() -> dict:
    """Scan all logs/trades_*.json and return executed orders keyed by ticker.

    If the same ticker appears across multiple records (e.g. partial fills
    across scans), counts are accumulated.
    Returns: {ticker: {"count": int, "limit_price": int, "placed_at": str}}
    """
    trades: dict = {}
    if not os.path.exists(config.LOG_DIR):
        return trades

    for fname in sorted(os.listdir(config.LOG_DIR)):
        if not (fname.startswith("trades_") and fname.endswith(".json")):
            continue
        path = os.path.join(config.LOG_DIR, fname)
        try:
            with open(path) as f:
                records = json.load(f)
            for r in records:
                if r.get("type") != "scan":
                    continue
                for e in r.get("executed", []):
                    if e.get("status") == "error":
                        continue
                    ticker = e["ticker"]
                    if ticker not in trades:
                        trades[ticker] = {
                            "count": 0,
                            "limit_price": e["limit_price"],
                            "placed_at": r["timestamp"],
                        }
                    trades[ticker]["count"] += e["count"]
        except Exception as ex:
            logger.warning(f"pnl_tracker: could not read {path}: {ex}")

    return trades


# ---------------------------------------------------------------------------
# Market resolution
# ---------------------------------------------------------------------------

def _check_market_result(ticker: str) -> str | None:
    """Returns 'yes', 'no', or None if market not yet settled."""
    try:
        data = public_get(config.KALSHI_API_BASE, f"/markets/{ticker}")
        market = data.get("market", data)
        result = market.get("result") or ""
        if result.lower() in ("yes", "no"):
            return result.lower()
    except Exception as e:
        logger.debug(f"pnl_tracker: fetch {ticker}: {e}")
    return None


# ---------------------------------------------------------------------------
# Main update
# ---------------------------------------------------------------------------

def update_pnl() -> dict:
    """
    Load all executed trades from logs, attempt to resolve any that haven't
    been settled yet, persist results, and return current stats.

    Returns stats dict:
      total_resolved, total_unresolved, wins, losses, win_rate,
      total_cost_cents, total_pnl_cents, roi_pct, newly_resolved (list)
    """
    store = _load_store()
    resolved: dict = store["resolved"]
    unresolved: dict = store["unresolved"]

    # Ingest new executed trades from logs
    all_trades = _load_all_executed_trades()
    for ticker, info in all_trades.items():
        if ticker not in resolved and ticker not in unresolved:
            unresolved[ticker] = info

    # Try to resolve unresolved trades
    newly_resolved = []
    for ticker in list(unresolved.keys()):
        result = _check_market_result(ticker)
        if result is None:
            continue
        info = unresolved[ticker]
        count = info["count"]
        cost_cents = count * info["limit_price"]
        revenue_cents = count * 100 if result == "yes" else 0
        pnl_cents = revenue_cents - cost_cents

        resolved[ticker] = {
            "count": count,
            "limit_price": info["limit_price"],
            "cost_cents": cost_cents,
            "revenue_cents": revenue_cents,
            "pnl_cents": pnl_cents,
            "result": result,
            "placed_at": info.get("placed_at"),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        del unresolved[ticker]
        newly_resolved.append(ticker)
        sign = "+" if pnl_cents >= 0 else ""
        logger.info(
            f"pnl_tracker: resolved {ticker} result={result} "
            f"pnl={sign}{cents_to_dollars(pnl_cents)}"
        )

    store["resolved"] = resolved
    store["unresolved"] = unresolved
    _save_store(store)

    wins = [v for v in resolved.values() if v["pnl_cents"] > 0]
    total_cost = sum(v["cost_cents"] for v in resolved.values())
    total_pnl = sum(v["pnl_cents"] for v in resolved.values())

    return {
        "total_resolved": len(resolved),
        "total_unresolved": len(unresolved),
        "wins": len(wins),
        "losses": len(resolved) - len(wins),
        "win_rate": len(wins) / len(resolved) if resolved else 0.0,
        "total_cost_cents": total_cost,
        "total_pnl_cents": total_pnl,
        "roi_pct": (total_pnl / total_cost * 100) if total_cost > 0 else 0.0,
        "newly_resolved": newly_resolved,
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_summary(stats: dict) -> str:
    lines = ["  P&L Summary"]
    n = stats["total_resolved"]
    pending = stats["total_unresolved"]
    lines.append(f"    Resolved trades : {n}  ({pending} pending settlement)")
    if n > 0:
        wr = stats["win_rate"] * 100
        lines.append(f"    Win rate        : {stats['wins']}/{n}  ({wr:.1f}%)")
        sign = "+" if stats["total_pnl_cents"] >= 0 else ""
        lines.append(f"    Total P&L       : {sign}{cents_to_dollars(stats['total_pnl_cents'])}")
        lines.append(f"    ROI             : {sign}{stats['roi_pct']:.1f}%")
    else:
        lines.append("    No resolved trades yet.")
    if stats["newly_resolved"]:
        lines.append(f"    Newly resolved  : {', '.join(stats['newly_resolved'])}")
    return "\n".join(lines)
