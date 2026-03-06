import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class BaseStrategy:
    """Base class for market strategies. Subclass per market category."""

    def evaluate(self, markets: list[dict], forecasts: dict,
                 max_trade_cents: int = None, max_exposure_cents: int = None) -> tuple[list[dict], list[dict]]:
        raise NotImplementedError


class WeatherStrategy(BaseStrategy):
    """
    10-step filter per spec. HARD_CEILING is never overrideable.
    """

    def evaluate(self, markets: list[dict], forecasts: dict,
                 max_trade_cents: int = None, max_exposure_cents: int = None,
                 available_balance_cents: int = None,
                 held_tickers: set = None,
                 held_city_dates: set = None) -> tuple[list[dict], list[dict]]:
        max_trade = max_trade_cents if max_trade_cents is not None else config.MAX_TRADE_CENTS
        max_exposure = max_exposure_cents if max_exposure_cents is not None else config.MAX_EXPOSURE_CENTS

        # 90% safety margin — never try to spend the last penny
        remaining_balance = int(available_balance_cents * 0.9) if available_balance_cents is not None else None

        _held_tickers = held_tickers or set()
        _held_city_dates = held_city_dates or set()

        signals = []
        skipped_details = []
        seen_city_dates = set()
        total_exposure = 0

        # Sort candidates: best edge first, soonest resolution first (requires two passes)
        candidates = self._score_candidates(markets, forecasts, max_trade)
        candidates.sort(key=lambda x: (-x["edge"], x["hours_to_resolution"]))

        for c in candidates:
            if len(signals) >= config.MAX_TRADES_PER_RUN:
                break

            # Pre-filter: skip tickers we already hold (survives restarts)
            if c["ticker"] in _held_tickers:
                reason = "already holding position"
                logger.info(f"strategy: SKIP {c['ticker']} — {reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": reason})
                continue

            if (c["city_key"], c["date"]) in _held_city_dates:
                reason = "already holding position on this date"
                logger.info(f"strategy: SKIP {c['ticker']} — {reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": reason})
                continue

            skip_reason = c.get("skip_reason")
            if skip_reason:
                logger.info(f"strategy: SKIP {c['ticker']} — {skip_reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": skip_reason})
                continue

            city_date = (c["city_key"], c["date"])
            if city_date in seen_city_dates:
                reason = "duplicate city+date signal"
                logger.info(f"strategy: SKIP {c['ticker']} — {reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": reason})
                continue

            trade_cost = c["count"] * c["limit_price"]
            if total_exposure + trade_cost > max_exposure:
                reason = "exceeds MAX_EXPOSURE"
                logger.info(f"strategy: SKIP {c['ticker']} — {reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": reason})
                continue

            if remaining_balance is not None and trade_cost > remaining_balance:
                reason = f"insufficient balance (${remaining_balance / 100:.2f} available)"
                logger.info(f"strategy: SKIP {c['ticker']} — {reason}")
                skipped_details.append({"ticker": c["ticker"], "reason": reason})
                continue

            seen_city_dates.add(city_date)
            total_exposure += trade_cost
            if remaining_balance is not None:
                remaining_balance -= trade_cost
            signals.append(c)

        return signals, skipped_details

    def _score_candidates(self, markets: list[dict], forecasts: dict, max_trade_cents: int) -> list[dict]:
        results = []
        for m in markets:
            city_key = m["city_key"]
            date = m["date"]
            ticker = m["ticker"]
            yes_price = m["yes_price"]
            bucket_low = m["bucket_low"]
            bucket_high = m["bucket_high"]
            hours = m["hours_to_resolution"]

            forecast = forecasts.get((city_key, date))

            # Step 1: match forecast
            if forecast is None:
                results.append({**m, "skip_reason": "no forecast available", "edge": -1})
                continue

            confidence = forecast["confidence"]
            temp = forecast["temp"]

            # Step 2: confidence == 0 → SKIP
            if confidence == 0:
                results.append({**m, "skip_reason": "confidence=0", "edge": -1})
                continue

            # Step 3: find bucket containing consensus_temp
            if temp is None or not (bucket_low <= temp < bucket_high):
                results.append({**m, "skip_reason": f"temp {temp} not in bucket [{bucket_low},{bucket_high})", "edge": -1})
                continue

            # Step 4: HARD CEILING — never overrideable
            if yes_price > config.HARD_CEILING:
                results.append({**m, "skip_reason": f"yes_price {yes_price}¢ > HARD_CEILING {config.HARD_CEILING}¢", "edge": -1})
                continue

            # Step 5: entry threshold
            if yes_price > config.ENTRY_THRESHOLD:
                results.append({**m, "skip_reason": f"yes_price {yes_price}¢ > ENTRY_THRESHOLD {config.ENTRY_THRESHOLD}¢", "edge": -1})
                continue

            # Step 6: edge check
            edge = confidence - (yes_price / 100)
            if edge < config.MIN_EDGE:
                results.append({**m, "skip_reason": f"edge {edge:.3f} < MIN_EDGE {config.MIN_EDGE}", "edge": edge})
                continue

            # Step 7: minimum confidence
            if confidence < config.MIN_CONFIDENCE:
                results.append({**m, "skip_reason": f"confidence {confidence:.2f} < MIN_CONFIDENCE {config.MIN_CONFIDENCE}", "edge": edge})
                continue

            limit_price = yes_price + 1
            count = max(1, max_trade_cents // limit_price)

            results.append({
                **m,
                "confidence": confidence,
                "consensus_temp": temp,
                "edge": edge,
                "limit_price": limit_price,
                "count": count,
                "skip_reason": None,
            })

        return results


def evaluate(markets: list[dict], forecasts: dict,
             max_trade_cents: int = None, max_exposure_cents: int = None,
             available_balance_cents: int = None,
             held_tickers: set = None,
             held_city_dates: set = None) -> tuple[list[dict], list[dict]]:
    """Top-level evaluate using WeatherStrategy (extensible). Returns (signals, skipped_details)."""
    strategy = WeatherStrategy()
    return strategy.evaluate(
        markets, forecasts, max_trade_cents, max_exposure_cents,
        available_balance_cents, held_tickers, held_city_dates,
    )
