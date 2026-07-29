"""V7 Market Data — fetches price, technicals, news for analysis."""
import os, json, time, requests, logging
from typing import Optional

logger = logging.getLogger(__name__)

class MarketDataProvider:
    """Aggregates market data from Delta Exchange and public sources."""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 5  # seconds

    def _delta_request(self, path: str) -> dict:
        api_key = os.getenv("DELTA_API_KEY", "")
        secret = os.getenv("DELTA_API_SECRET", "")
        base = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")
        import hmac, hashlib
        timestamp = int(time.time() * 1000)
        sig = hmac.new(secret.encode(), f"GET{path}{timestamp}".encode(), hashlib.sha256).hexdigest()
        try:
            resp = requests.get(f"{base}{path}", headers={
                "api-key": api_key, "timestamp": str(timestamp),
                "signature": sig,
            }, timeout=8)
            if resp.status_code == 200:
                return resp.json().get("result", {})
        except:
            pass
        return {}

    def get_ticker(self, symbol: str) -> dict:
        """Get current price and 24h stats."""
        data = self._delta_request(f"/v2/tickers/{symbol}")
        if isinstance(data, dict):
            return {
                "price": float(data.get("mark_price", 0) or data.get("last_price", 0)),
                "volume_24h": float(data.get("volume_24h", 0)),
                "high_24h": float(data.get("high_24h", 0)),
                "low_24h": float(data.get("low_24h", 0)),
                "change_24h": float(data.get("change_24h", 0) or 0),
                "funding_rate": float(data.get("funding_rate", 0) or 0),
                "open_interest": float(data.get("open_interest", 0) or 0),
                "volatility_24h": float(data.get("mark_volatility", 0) or 0),
            }
        return {"price": 0, "volume_24h": 0, "funding_rate": 0, "open_interest": 0, "volatility_24h": 0}

    def get_technical(self, symbol: str) -> dict:
        """Fetch technical indicators from mainnet candles."""
        ticker = self.get_ticker(symbol)
        price = ticker.get("price", 0)

        # Fetch candles from mainnet (no auth required, need start/end)
        closes, highs, lows, volumes = [], [], [], []
        try:
            import time as _time
            end_ts = int(_time.time())
            start_ts = end_ts - 365 * 86400  # 1 year back
            url = f"https://cdn.deltaex.org/v2/history/candles?resolution=4h&symbol={symbol}&start={start_ts}&end={end_ts}&limit=100"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                raw = resp.json()
                if isinstance(raw, list):
                    for c in raw:
                        close = float(c.get("close", 0))
                        if close > 0:
                            closes.append(close)
                            highs.append(float(c.get("high", 0)))
                            lows.append(float(c.get("low", 0)))
                            volumes.append(float(c.get("volume", 0)))
                elif isinstance(raw, dict):
                    data = raw.get("result", raw.get("data", []))
                    for c in data:
                        close = float(c.get("close", 0))
                        if close > 0:
                            closes.append(close)
                            highs.append(float(c.get("high", 0)))
                            lows.append(float(c.get("low", 0)))
                            volumes.append(float(c.get("volume", 0)))
        except Exception as e:
            logger.warning(f"Candle fetch failed: {e}")

        if len(closes) < 14:
            return {"rsi": 50, "macd_histogram": 0, "bb_upper": price * 1.02,
                    "bb_mid": price, "bb_lower": price * 0.98,
                    "ema_9": price, "ema_21": price, "volatility_24h": 0}

        # Compute volatility from 24h range
        vol = ((max(highs[-6:], default=price) - min(lows[-6:], default=price)) / price * 100) if price else 0

        closes = closes[::-1]  # oldest first

        # RSI
        gains, losses = 0, 0
        for i in range(1, 15):
            diff = closes[-i] - closes[-i-1]
            if diff >= 0: gains += diff
            else: losses += abs(diff)
        avg_gain = gains / 14
        avg_loss = losses / 14
        rsi = 50 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

        # EMA
        ema9 = self._ema(closes, 9)
        ema21 = self._ema(closes, 21)

        # MACD
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd = ema12 - ema26
        macd_signal = self._ema([ema12, ema26], 9) if False else ema26  # simplified
        macd_hist = macd - ema26

        # Bollinger
        sma20 = sum(closes[-20:]) / min(20, len(closes))
        variance = sum((c - sma20)**2 for c in closes[-20:]) / min(20, len(closes))
        std = variance ** 0.5
        bb_up = sma20 + 2 * std
        bb_low = sma20 - 2 * std

        return {
            "rsi": rsi,
            "macd_histogram": macd_hist,
            "bb_upper": bb_up,
            "bb_mid": sma20,
            "bb_lower": bb_low,
            "ema_9": ema9,
            "ema_21": ema21,
            "volatility_24h": vol,
        }

    def _ema(self, data: list, period: int) -> float:
        if len(data) < period:
            return sum(data) / len(data) if data else 0
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def get_market_data(self, symbol: str) -> dict:
        """Complete market data package for analysis."""
        ticker = self.get_ticker(symbol)
        technical = self.get_technical(symbol)
        return {
            **ticker,
            "technical": technical,
            "volatility_24h": technical.get("volatility_24h", ticker.get("volatility_24h", 0)),
            "regime": "trending" if technical.get("ema_9", 0) > technical.get("ema_21", 0) else "ranging",
            "news_headlines": [],
            "news_global": [],
            "social_sentiment": self._estimate_sentiment(ticker),
            "fear_greed": self._fear_greed(ticker),
            "macro_events": {},
        }

    def _estimate_sentiment(self, ticker: dict) -> str:
        change = ticker.get("change_24h", 0)
        if change > 3: return "greedy"
        if change > 1: return "slightly bullish"
        if change < -3: return "fearful"
        if change < -1: return "slightly bearish"
        return "neutral"

    def _fear_greed(self, ticker: dict) -> int:
        """Simple fear-greed approximation from price action."""
        change = ticker.get("change_24h", 0)
        vol = ticker.get("volatility_24h", 2)
        fg = 50 + (change * 2) - (vol * 0.5)
        return max(10, min(90, int(fg)))
