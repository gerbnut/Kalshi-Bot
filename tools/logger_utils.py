import json
import logging
import os
from datetime import datetime, timezone

import config
from tools.utils import cents_to_dollars

logger = logging.getLogger(__name__)


class ScanLogger:
    def __init__(self):
        self.scan_count = 0
        self.session_stats = {
            "total_signals": 0,
            "total_executed": 0,
            "total_skipped": 0,
        }

    def _log_path(self) -> str:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(config.LOG_DIR, f"trades_{today}.json")

    def _append_record(self, record: dict):
        path = self._log_path()
        records = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    records = json.load(f)
            except Exception:
                records = []
        records.append(record)
        with open(path, "w") as f:
            json.dump(records, f, indent=2, default=str)

    def log_scan(
        self,
        scan_num: int,
        markets: list[dict],
        signals: list[dict],
        executed: list[dict],
        skipped_details: list[dict],
        balance_cents: int,
        exposure_cents: int,
    ):
        ts = datetime.now(timezone.utc).isoformat()
        self.session_stats["total_signals"] += len(signals)
        self.session_stats["total_executed"] += len(executed)
        self.session_stats["total_skipped"] += len(skipped_details)

        record = {
            "type": "scan",
            "timestamp": ts,
            "scan_num": scan_num,
            "markets_scanned": len(markets),
            "signals_generated": len(signals),
            "executed": [
                {
                    "ticker": e["ticker"],
                    "count": e["count"],
                    "limit_price": e["limit_price"],
                    "order_id": e.get("order_id"),
                    "status": e.get("status"),
                }
                for e in executed
            ],
            "skipped_details": skipped_details,
            "balance_cents": balance_cents,
            "exposure_cents": exposure_cents,
        }
        self._append_record(record)

        # Terminal summary
        print(f"\n{'═'*60}")
        print(f"  SCAN #{scan_num}  |  {ts}")
        print(f"  Markets: {len(markets)}  |  Signals: {len(signals)}  |  Executed: {len(executed)}")
        print(f"  Balance: {cents_to_dollars(balance_cents)}  |  Exposure: {cents_to_dollars(exposure_cents)}")
        if executed:
            print("  Orders:")
            for e in executed:
                status = e.get("status", "?")
                print(f"    {e['ticker']} {e['count']}x @ {e['limit_price']}¢  [{status}]")
        if skipped_details:
            print(f"  Skipped: {len(skipped_details)} markets")
            for s in skipped_details[:3]:
                print(f"    {s.get('ticker', '?')}: {s.get('reason', '?')}")
            if len(skipped_details) > 3:
                print(f"    ... and {len(skipped_details) - 3} more")
        print(f"{'═'*60}")

    def log_error(self, context: str, error: Exception):
        ts = datetime.now(timezone.utc).isoformat()
        record = {
            "type": "error",
            "timestamp": ts,
            "context": context,
            "error": str(error),
        }
        self._append_record(record)
        logger.error(f"logger_utils: {context}: {error}")
