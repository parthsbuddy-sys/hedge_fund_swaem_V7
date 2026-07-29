"""V7 Execution — Order models, broker interface, risk sizing."""
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market_order"
    LIMIT = "limit_order"
    STOP = "stop_order"

class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

@dataclass
class TradeSetup:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    filled_quantity: float
    fill_price: float
    status: OrderStatus
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DeltaBroker:
    """Delta Exchange broker adapter — crypto perps execution."""

    def __init__(self, account: int = 1):
        import os
        suffix = f"_{account}" if account > 1 else ""
        self.api_key = os.getenv(f"DELTA_API_KEY{suffix}", "")
        self.secret = os.getenv(f"DELTA_API_SECRET{suffix}", "")
        self.base_url = os.getenv(f"DELTA_BASE_URL{suffix}",
                                  os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org"))
        self.timeout = 10
        self.account = account
        self.name = f"Account #{account}"

    def _sign(self, method: str, path: str, body: str = "") -> dict:
        import hmac, hashlib, time
        timestamp = int(time.time())
        sig_data = f"{method}{timestamp}{path}{body}"
        signature = hmac.new(
            self.secret.encode(), sig_data.encode(), hashlib.sha256
        ).hexdigest()
        return {
            "api-key": self.api_key,
            "timestamp": str(timestamp),
            "signature": signature,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        import requests, traceback
        body_str = json.dumps(body) if body else ""
        headers = self._sign(method, path, body_str)
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=headers, data=body_str, timeout=self.timeout)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {"success": True, "data": data.get("result", data)}
            else:
                return {"success": False, "error": data.get("error", data.get("message", "unknown")), "status": resp.status_code, "_full": str(data.get("error", {}))[:500]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_wallet(self) -> dict:
        result = self._request("GET", "/v2/wallet/balances")
        if result.get("success"):
            for bal in result.get("data", []):
                sym = bal.get("asset_symbol", "") or bal.get("asset", {}).get("symbol", "")
                if sym in ("USDT", "USD"):
                    return {
                        "balance": float(bal.get("balance", 0)),
                        "available": float(bal.get("available_balance", 0)),
                        "margin": float(bal.get("position_margin", 0)) + float(bal.get("order_margin", 0)),
                    }
        return {"balance": 0, "available": 0, "margin": 0}

    def get_positions(self) -> list:
        result = self._request("GET", "/v2/positions/margined")
        positions = []
        if result.get("success"):
            for p in result.get("data", []):
                size = float(p.get("size", 0))
                if size != 0:
                    positions.append({
                        "symbol": p.get("product", {}).get("symbol", ""),
                        "size": size,
                        "entry": float(p.get("entry_price", 0)),
                        "mark": float(p.get("mark_price", 0)),
                        "pnl": float(p.get("unrealized_pnl", 0)),
                        "margin": float(p.get("margin", 0)),
                    })
        return positions

    def place_order(self, setup: TradeSetup) -> OrderResult:
        """Place an order on Delta Exchange."""
        # Use product_id lookup — simpler approach with symbol
        product_symbol = setup.symbol
        if not product_symbol.endswith("USD"):
            product_symbol += "USD"

        # Build order body
        order_body = {
            "product_symbol": product_symbol,
            "order_type": setup.order_type.value,
            "side": setup.side.value,
            "size": int(abs(setup.quantity)),
        }

        # Add bracket stop-loss / take-profit (price in quote currency)
        if setup.price and setup.price > 0:
            if setup.stop_loss and setup.stop_loss > 0:
                sl_pct = setup.stop_loss / 100.0
                if setup.side == OrderSide.BUY:
                    order_body["bracket_stop_loss_price"] = round(setup.price * (1 - sl_pct), 2)
                else:
                    order_body["bracket_stop_loss_price"] = round(setup.price * (1 + sl_pct), 2)
                print(f"      SL: ${order_body['bracket_stop_loss_price']:.2f} ({setup.stop_loss:.1f}%)")

            if setup.take_profit and setup.take_profit > 0:
                tp_pct = setup.take_profit / 100.0
                if setup.side == OrderSide.BUY:
                    order_body["bracket_take_profit_price"] = round(setup.price * (1 + tp_pct), 2)
                else:
                    order_body["bracket_take_profit_price"] = round(setup.price * (1 - tp_pct), 2)
                print(f"      TP: ${order_body['bracket_take_profit_price']:.2f} ({setup.take_profit:.1f}%)")

        result = self._request("POST", "/v2/orders", order_body)

        # If bracket order rejected because position exists, retry without brackets
        if not result.get("success"):
            err_code = ""
            err_data = result.get("error", {})
            if isinstance(err_data, dict):
                err_code = err_data.get("code", "")
            elif isinstance(err_data, str):
                err_code = err_data
            if "bracket_order_position_exists" in str(err_code):
                print(f"      ⚠️  Bracket order not supported on existing position — retrying without SL/TP")
                order_body.pop("bracket_stop_loss_price", None)
                order_body.pop("bracket_take_profit_price", None)
                result = self._request("POST", "/v2/orders", order_body)

        if result.get("success"):
            data = result.get("data", {})
            raw_state = str(data.get("state", "")).lower()
            filled = float(data.get("filled_size", 0) or 0)
            avg_price = float(data.get("average_fill_price", setup.price or 0) or 0)
            order_id = str(data.get("id", ""))

            if raw_state in ("filled", "closed") or filled > 0:
                status = OrderStatus.FILLED
            elif raw_state in ("pending", "open", "active"):
                status = OrderStatus.PENDING if filled == 0 else OrderStatus.PARTIAL
            else:
                status = OrderStatus.PENDING

            return OrderResult(
                order_id=order_id, symbol=setup.symbol,
                side=setup.side, quantity=setup.quantity,
                filled_quantity=filled, fill_price=avg_price,
                status=status
            )
        else:
            return OrderResult(
                order_id="", symbol=setup.symbol,
                side=setup.side, quantity=setup.quantity,
                filled_quantity=0, fill_price=0,
                status=OrderStatus.REJECTED,
                error=result.get("error", "unknown")
            )

    def close_all_positions(self) -> list:
        """Close all open positions."""
        positions = self.get_positions()
        results = []
        for p in positions:
            side = OrderSide.SELL if p["size"] > 0 else OrderSide.BUY
            setup = TradeSetup(
                symbol=p["symbol"], side=side,
                quantity=abs(p["size"]), order_type=OrderType.MARKET,
                reason="V7 close_all"
            )
            results.append(self.place_order(setup))
        return results

    def close_position(self, symbol: str) -> dict:
        """Close a specific position by symbol."""
        positions = self.get_positions()
        for p in positions:
            if p["symbol"] == symbol:
                side = OrderSide.SELL if p["size"] > 0 else OrderSide.BUY
                setup = TradeSetup(
                    symbol=symbol, side=side,
                    quantity=abs(p["size"]), order_type=OrderType.MARKET,
                    reason="V7 risk close"
                )
                return self.place_order(setup)
        return {"error": "position not found"}

import json  # needed for _request
