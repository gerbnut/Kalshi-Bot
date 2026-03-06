"""
Alerting — Discord and/or Telegram webhooks.

Configure in .env:
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
  TELEGRAM_BOT_TOKEN=123456:ABC...
  TELEGRAM_CHAT_ID=-100...

Both are optional. If neither is set, all alert calls are silent no-ops.
"""
import logging
import os

import requests

from tools.utils import cents_to_dollars

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level send
# ---------------------------------------------------------------------------

def _send_discord(msg: str):
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        requests.post(url, json={"content": msg[:2000]}, timeout=5)
    except Exception as e:
        logger.warning(f"alerting: discord failed: {e}")


def _send_telegram(msg: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg[:4096]}, timeout=5)
    except Exception as e:
        logger.warning(f"alerting: telegram failed: {e}")


def send(msg: str):
    """Send to all configured channels. Silent no-op if none configured."""
    _send_discord(msg)
    _send_telegram(msg)


# ---------------------------------------------------------------------------
# Named alert types
# ---------------------------------------------------------------------------

def alert_startup(balance_cents: int, config_summary: str):
    send(f"[BOT STARTED]\nBalance: {cents_to_dollars(balance_cents)}\n{config_summary}")


def alert_trade_placed(ticker: str, count: int, limit_price: int, order_id, status: str):
    send(
        f"[TRADE PLACED]\n"
        f"{ticker}\n"
        f"{count}x @ {limit_price}¢  (cost: {cents_to_dollars(count * limit_price)})\n"
        f"order_id={order_id}  status={status}"
    )


def alert_trade_failed(ticker: str, error: str):
    send(f"[ORDER FAILED]\n{ticker}\n{error}")


def alert_first_scan_summary(scan_num: int, markets_found: int, signals_count: int, skip_reasons: list[dict]):
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
):
    lines = [
        "[DAILY SUMMARY]",
        f"Scans: {scan_count}  |  Orders placed: {session_orders}",
        f"Balance: {cents_to_dollars(balance_cents)}",
    ]
    n = pnl_stats.get("total_resolved", 0)
    if n > 0:
        sign = "+" if pnl_stats["total_pnl_cents"] >= 0 else ""
        lines.append(
            f"Win rate: {pnl_stats['wins']}/{n} ({pnl_stats['win_rate']*100:.1f}%)  |  "
            f"P&L: {sign}{cents_to_dollars(pnl_stats['total_pnl_cents'])}  |  "
            f"ROI: {sign}{pnl_stats['roi_pct']:.1f}%"
        )
    else:
        lines.append("No resolved trades yet.")
    send("\n".join(lines))
