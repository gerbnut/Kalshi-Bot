# SOP: Evaluate Edge

## Purpose
Apply strategy filters to produce a ranked list of trade signals.

## 10-Step Filter (in order)

For each market:

1. **Match forecast** — Look up `(city_key, date)` in forecasts dict.
   If missing → SKIP: "no forecast available"

2. **Confidence gate** — If `confidence == 0` → SKIP: "confidence=0"

3. **Bucket match** — Check `bucket_low <= consensus_temp < bucket_high`.
   If not → SKIP: "temp not in bucket"

4. **Hard ceiling** — If `yes_price > HARD_CEILING (20¢)` → SKIP.
   **NEVER OVERRIDE THIS CHECK. It cannot be changed by config alone.**

5. **Entry threshold** — If `yes_price > ENTRY_THRESHOLD (15¢)` → SKIP.

6. **Edge minimum** — Compute `edge = confidence − (yes_price / 100)`.
   If `edge < MIN_EDGE (0.10)` → SKIP.

7. **Confidence minimum** — If `confidence < MIN_CONFIDENCE (0.40)` → SKIP.

8. **Exposure cap** — If `total_exposure + trade_cost > MAX_EXPOSURE_CENTS` → SKIP.
   (Checked cumulatively as signals are accepted.)

9. **Duplicate city+date** — If another signal already accepted for same city+date → SKIP.

10. **Accept signal** — All checks pass:
    - `limit_price = yes_price + 1`
    - `count = MAX_TRADE_CENTS // limit_price`
    - Emit signal dict

## Sorting
Sort accepted signals: **edge descending**, then **hours_to_resolution ascending**.
Cap at `MAX_TRADES_PER_RUN`.

## NEVER OVERRIDE RULES
- Steps 4 (HARD_CEILING) and 8 (MAX_EXPOSURE_CENTS) are hard blocks.
- These checks CANNOT be bypassed by modifying config values alone.
- The HARD_CEILING=20¢ limit exists to prevent accidental overpayment.
- The MAX_EXPOSURE_CENTS cap exists to prevent runaway session losses.

## Notes
- All prices in cents throughout
- Log SKIP reason for every filtered market
