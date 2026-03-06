import time
import base64
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_request(private_key, timestamp_str: str, method: str, path: str) -> str:
    """Sign method+timestamp+path (path stripped of query params) using RSA-PSS."""
    # Strip query params before signing
    path_no_query = path.split("?")[0]
    message = (timestamp_str + method.upper() + path_no_query).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


class KalshiClient:
    def __init__(self, api_base: str, key_id: str, private_key_path: str):
        self.api_base = api_base.rstrip("/")
        self.key_id = key_id
        self.private_key = load_private_key(private_key_path)

    def _headers(self, method: str, path: str) -> dict:
        ts = str(int(time.time() * 1000))
        # Kalshi requires the full path including /trade-api/v2 prefix for signing
        full_path = "/trade-api/v2" + path if not path.startswith("/trade-api") else path
        sig = sign_request(self.private_key, ts, method, full_path)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "Content-Type": "application/json",
        }

    def get(self, path: str) -> dict:
        headers = self._headers("GET", path)
        url = self.api_base + path
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict) -> dict:
        headers = self._headers("POST", path)
        url = self.api_base + path
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> dict:
        return self.get("/portfolio/balance")

    def get_positions(self) -> dict:
        return self.get("/portfolio/positions")

    def get_exchange_status(self) -> dict:
        return self.get("/exchange/status")

    def place_order(self, ticker: str, side: str, yes_price_cents: int, count: int) -> dict:
        from tools.utils import build_client_order_id
        body = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "type": "limit",
            "yes_price": yes_price_cents,
            "count": count,
            "client_order_id": build_client_order_id(),
        }
        return self.post("/portfolio/orders", body)


def public_get(api_base: str, path: str) -> dict:
    """Unauthenticated GET for public market data endpoints."""
    url = api_base.rstrip("/") + path
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()
