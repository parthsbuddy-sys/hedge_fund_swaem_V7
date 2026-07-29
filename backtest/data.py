"""Backtest Data — loads historical candles from Delta Exchange mainnet."""
import os, time, json, requests
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Candle:
    """Single OHLCV candle."""
    time: int       # Unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.time, tz=timezone.utc)

    @property
    def return_pct(self) -> float:
        return ((self.close - self.open) / self.open) * 100


class HistoricalDataLoader:
    """Fetches historical candles from Delta mainnet (no auth needed)."""

    BASE = "https://cdn.deltaex.org"

    def __init__(self, symbol: str = "BTCUSD"):
        self.symbol = symbol

    def fetch(self, resolution: str = "4h", lookback_days: int = 365) -> List[Candle]:
        """Fetch candles from Delta mainnet."""
        now = int(time.time())
        start = now - lookback_days * 86400

        params = {
            "symbol": self.symbol,
            "resolution": resolution,
            "start": str(start),
            "end": str(now),
        }

        resp = requests.get(f"{self.BASE}/v2/history/candles",
                            params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch data: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        raw = data.get("result", [])
        if not raw:
            raise RuntimeError(f"No data returned for {self.symbol}")

        candles = []
        for c in raw:
            candles.append(Candle(
                time=c["time"],
                open=float(c.get("open", 0)),
                high=float(c.get("high", 0)),
                low=float(c.get("low", 0)),
                close=float(c.get("close", 0)),
                volume=float(c.get("volume", 0)),
            ))

        # Sort oldest first
        candles.sort(key=lambda c: c.time)
        return candles

    def fetch_multi(self, symbols: List[str], resolution: str = "4h",
                    lookback_days: int = 365) -> dict:
        """Fetch candles for multiple symbols."""
        result = {}
        for sym in symbols:
            try:
                result[sym] = self.fetch(sym, resolution, lookback_days)
                print(f"  {sym}: {len(result[sym])} candles ({resolution})")
            except Exception as e:
                print(f"  {sym}: FAILED — {e}")
        return result
