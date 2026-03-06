import logging

import config
from tools.utils import cents_to_dollars

logger = logging.getLogger(__name__)


def startup_check(client) -> int:
    """Verify exchange status, print balance and open positions. Returns balance_cents."""
    try:
        status = client.get_exchange_status()
        trading_active = status.get("trading_active", False)
        exchange_active = status.get("exchange_active", False)
        print(f"\n{'='*60}")
        print(f"  Exchange status: trading_active={trading_active}  exchange_active={exchange_active}")
    except Exception as e:
        print(f"\nWARNING: Could not fetch exchange status: {e}")

    balance_cents = 0
    try:
        bal = client.get_balance()
        balance_cents = bal.get("balance", 0)
        print(f"  Balance: {cents_to_dollars(balance_cents)}")
    except Exception as e:
        print(f"  WARNING: Could not fetch balance: {e}")

    try:
        positions = client.get_positions()
        pos_list = positions.get("market_positions", []) or positions.get("positions", [])
        print(f"  Open positions: {len(pos_list)}")
        for p in pos_list[:5]:
            ticker = p.get("ticker", "?")
            qty = p.get("position", p.get("quantity", "?"))
            print(f"    {ticker}: {qty} contracts")
        if len(pos_list) > 5:
            print(f"    ... and {len(pos_list) - 5} more")
    except Exception as e:
        print(f"  WARNING: Could not fetch positions: {e}")

    print(f"{'='*60}\n")
    return balance_cents


def execute_signals(client, signals: list[dict]) -> list[dict]:
    """Place limit orders for each signal. Returns list of executed order records."""
    executed = []
    for sig in signals:
        ticker = sig["ticker"]
        limit_price = sig["limit_price"]
        count = sig["count"]
        try:
            resp = client.place_order(
                ticker=ticker,
                side="yes",
                yes_price_cents=limit_price,
                count=count,
            )
            order_id = resp.get("order", {}).get("order_id") or resp.get("order_id", "?")
            status = resp.get("order", {}).get("status") or resp.get("status", "?")
            print(
                f"  ORDER PLACED: {ticker} | {count}x @ {limit_price}¢ | "
                f"order_id={order_id} status={status}"
            )
            logger.info(f"executor: order placed {ticker} count={count} price={limit_price}¢ resp={resp}")
            executed.append({
                "ticker": ticker,
                "count": count,
                "limit_price": limit_price,
                "order_id": order_id,
                "status": status,
                "response": resp,
            })
        except Exception as e:
            logger.error(f"executor: order failed {ticker}: {e}")
            print(f"  ORDER FAILED: {ticker} — {e}")
            # Log the failure but continue — never retry immediately
            executed.append({
                "ticker": ticker,
                "count": count,
                "limit_price": limit_price,
                "order_id": None,
                "status": "error",
                "error": str(e),
            })
    return executed


def session_summary(client, initial_balance_cents: int):
    """Print updated balance and delta vs session start."""
    try:
        bal = client.get_balance()
        current = bal.get("balance", 0)
        delta = current - initial_balance_cents
        sign = "+" if delta >= 0 else ""
        print(f"\n  Session balance: {cents_to_dollars(current)} ({sign}{cents_to_dollars(delta)})")
    except Exception as e:
        print(f"\n  WARNING: Could not fetch final balance: {e}")
