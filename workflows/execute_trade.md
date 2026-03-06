# SOP: Execute Trade

## Purpose
Place limit orders on Kalshi for each accepted signal.

## Steps

1. **Startup check** (once per session):
   - `GET /exchange/status` → verify `trading_active=true`
   - `GET /portfolio/balance` → print balance
   - `GET /portfolio/positions` → print open positions

2. **Place order** (per signal):
   - `POST /portfolio/orders`
   - Body:
     ```json
     {
       "ticker": "<ticker>",
       "action": "buy",
       "side": "yes",
       "type": "limit",
       "yes_price": <limit_price_cents>,
       "count": <count>,
       "client_order_id": "<uuid4>"
     }
     ```

3. **Log response** — Log full response (success or error) to daily JSON file.

4. **On failure** — Log error dict and continue to next signal.
   Never retry immediately. Never raise and abort the session.

5. **Session summary** — After all signals processed, print:
   - Updated balance
   - Delta vs session start

## Notes
- Always use fresh `uuid4()` as `client_order_id` — do not reuse
- `yes_price` = `limit_price` from signal (always `original_yes_price + 1`)
- Auth: RSA-PSS signed headers required; sign path WITHOUT query params
- Public data endpoints (scanning) require NO auth headers
