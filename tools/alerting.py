"""
Alerting — Discord embeds and/or Telegram webhooks.

Configure in .env:
  DISCORD_WEBHOOK_URL      — trade alerts channel (per-order notifications)
  DISCORD_PL_WEBHOOK_URL   — P&L channel (daily summary)
  TELEGRAM_BOT_TOKEN=123456:ABC...
  TELEGRAM_CHAT_ID=-100...

All are optional. If not set, calls are silent no-ops.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from tools.utils import cents_to_dollars

logger = logging.getLogger(__name__)

# Discord embed colors
_GREEN = 0x2ECC71
_RED   = 0xE74C3C
_BLUE  = 0x3498DB

_CITY_NAMES = {
    "KXHIGHNY":   "New York",
    "KXHIGHCHI":  "Chicago",
    "KXHIGHTDAL": "Dallas",
    "KXHIGHMIA":  "Miami",
    "KXHIGHLAX":  "Los Angeles",
}
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5,  "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_ticker(ticker: str) -> tuple[str, str]:
    """Parse 'KXHIGHMIA-26MAR06-B80.5' → ('Miami', 'Mar 06, 2026')."""
    try:
        parts = ticker.split("-")
        city = _CITY_NAMES.get(parts[0], parts[0])
        raw = parts[1]  # e.g. "26MAR06"
        year  = int("20" + raw[:2])
        month = _MONTHS.get(raw[2:5], 1)
        day   = int(raw[5:7])
        from datetime import date
        date_str = date(year, month, day).strftime("%b %d, %Y")
        return city, date_str
    except Exception:
        return ticker, ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Low-level send helpers
# ---------------------------------------------------------------------------

def _send_discord_embed(embed: dict, webhook_url: str):
    """Post a single embed to a webhook URL. Silent no-op on any failure."""
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logger.warning(f"alerting: discord embed failed: {e}")


def _send_discord(msg: str):
    """Send plain-text message to the trade alerts webhook."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        requests.post(url, json={"content": msg[:2000]}, timeout=5)
    except Exception as e:
        logger.warning(f"alerting: discord failed: {e}")


def _send_telegram(msg: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg[:4096]}, timeout=5)
    except Exception as e:
        logger.warning(f"alerting: telegram failed: {e}")


def send(msg: str):
    """Send plain text to all configured channels. Silent no-op if none configured."""
    _send_discord(msg)
    _send_telegram(msg)


# ---------------------------------------------------------------------------
# Named alert types
# ---------------------------------------------------------------------------

def alert_startup(balance_cents: int, config_summary: str):
    send(f"[BOT STARTED]\nBalance: {cents_to_dollars(balance_cents)}\n{config_summary}")


def alert_trade_placed(ticker: str, count: int, limit_price: int, order_id,
                       status: str, balance_after: int = None):
    trade_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    city, date_str = _parse_ticker(ticker)
    cost_cents = count * limit_price

    fields = [
        {"name": "Market",    "value": f"`{ticker}`",                          "inline": False},
        {"name": "City",      "value": city,                                   "inline": True},
        {"name": "Date",      "value": date_str,                               "inline": True},
        {"name": "Position",  "value": f"{count} contracts @ {limit_price}¢",  "inline": True},
        {"name": "Cost",      "value": cents_to_dollars(cost_cents),           "inline": True},
        {"name": "Status",    "value": status,                                 "inline": True},
        {"name": "Order ID",  "value": str(order_id),                         "inline": True},
    ]
    if balance_after is not None:
        fields.append({"name": "Balance After", "value": cents_to_dollars(balance_after), "inline": True})

    embed = {
        "title": "Trade Placed",
        "color": _GREEN,
        "fields": fields,
        "timestamp": _now_iso(),
    }
    _send_discord_embed(embed, trade_url)
    _send_telegram(
        f"[TRADE PLACED] {ticker}\n{count}x @ {limit_price}¢  cost={cents_to_dollars(cost_cents)}"
    )


def alert_trade_failed(ticker: str, error: str):
    trade_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    city, date_str = _parse_ticker(ticker)

    embed = {
        "title": "Order Failed",
        "color": _RED,
        "fields": [
            {"name": "Market", "value": f"`{ticker}`", "inline": False},
            {"name": "City",   "value": city,           "inline": True},
            {"name": "Date",   "value": date_str,        "inline": True},
            {"name": "Error",  "value": error[:1000],    "inline": False},
        ],
        "timestamp": _now_iso(),
    }
    _send_discord_embed(embed, trade_url)
    _send_telegram(f"[ORDER FAILED] {ticker}\n{error}")


def alert_first_scan_summary(scan_num: int, markets_found: int, signals_count: int,
                              skip_reasons: list[dict]):
    top_skips = skip_reasons[:5]
    skip_lines = "\n".join(f"  • {s['ticker']}: {s['reason']}" for s in top_skips)
    if len(skip_reasons) > 5:
        skip_lines += f"\n  ... and {len(skip_reasons) - 5} more"
    lines = [
        f"[SCAN #{scan_num} SUMMARY]",
        f"Markets found: {markets_found}  |  Signals: {signals_count}  |  Skipped: {len(skip_reasons)}",
    ]
    if skip_lines:
        lines.append(f"Top skip reasons:\n{skip_lines}")
    send("\n".join(lines))


def alert_daily_summary(
    scan_count: int,
    session_orders: int,
    balance_cents: int,
    pnl_stats: dict,
    positions: list = None,
):
    pl_url = os.environ.get("DISCORD_PL_WEBHOOK_URL", "").strip()

    n = pnl_stats.get("total_resolved", 0)
    pending = pnl_stats.get("total_unresolved", 0)

    if n > 0:
        sign = "+" if pnl_stats["total_pnl_cents"] >= 0 else ""
        pnl_str = (
            f"{pnl_stats['wins']}/{n} wins ({pnl_stats['win_rate']*100:.1f}%)  |  "
            f"P&L: {sign}{cents_to_dollars(pnl_stats['total_pnl_cents'])}  |  "
            f"ROI: {sign}{pnl_stats['roi_pct']:.1f}%"
        )
    else:
        pnl_str = "No resolved trades yet."

    fields = [
        {"name": "Scans",          "value": str(scan_count),                    "inline": True},
        {"name": "Orders Placed",  "value": str(session_orders),                "inline": True},
        {"name": "Balance",        "value": cents_to_dollars(balance_cents),    "inline": True},
        {"name": "Settled Trades", "value": str(n),                             "inline": True},
        {"name": "Pending",        "value": str(pending),                       "inline": True},
        {"name": "P&L",            "value": pnl_str,                            "inline": False},
    ]

    if positions:
        pos_lines = "\n".join(
            f"{p.get('ticker', '?')}: {p.get('position', p.get('quantity', '?'))} contracts"
            for p in positions[:10]
        )
        if len(positions) > 10:
            pos_lines += f"\n... and {len(positions) - 10} more"
        fields.append({"name": f"Open Positions ({len(positions)})", "value": pos_lines, "inline": False})
    else:
        fields.append({"name": "Open Positions", "value": "None", "inline": True})

    newly = pnl_stats.get("newly_resolved", [])
    if newly:
        fields.append({"name": "Resolved Today", "value": ", ".join(newly), "inline": False})

    embed = {
        "title": "Daily P&L Summary",
        "color": _BLUE,
        "fields": fields,
        "timestamp": _now_iso(),
    }
    _send_discord_embed(embed, pl_url)

    # Also post plain-text to Telegram
    lines = [
        "[DAILY SUMMARY]",
        f"Scans: {scan_count}  |  Orders: {session_orders}",
        f"Balance: {cents_to_dollars(balance_cents)}",
        pnl_str,
    ]
    _send_telegram("\n".join(lines))
