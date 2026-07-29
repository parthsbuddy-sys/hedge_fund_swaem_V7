"""V7 Backtest Engine — runs the multi-agent pipeline against historical data."""
import os, sys, time, json, math
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# Backtest engine root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from backtest.data import HistoricalDataLoader, Candle
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.base_agent import LLMProvider
from agents.analyst_team import (
    FundamentalsAnalyst, SentimentAnalyst, NewsAnalyst, TechnicalAnalyst
)
from agents.researcher_team import BullishResearcher, BearishResearcher
from agents.trader import TraderAgent
from agents.risk_manager import RiskManager
from agents.portfolio_manager import PortfolioManager


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_time: int
    entry_price: float
    size_pct: float   # fraction of initial_balance
    sl_pct: float     # stop loss percent
    tp_pct: float     # take profit percent
    confidence: float
    exit_time: int = 0
    exit_price: float = 0
    exit_reason: str = "open"
    pnl_pct: float = 0
    pnl_usd: float = 0


class BacktestEngine:
    """Runs V7 multi-agent AI pipeline against historical candle data."""

    def __init__(self, initial_balance: float = 576.89):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.trades: List[BacktestTrade] = []
        self.open_trades: List[BacktestTrade] = []
        self.equity_curve: list = []
        self.tick_count = 0

    def compute_technicals(self, candles: List[Candle], idx: int) -> dict:
        """Compute technical indicators from candle history."""
        c = candles[idx]
        closes = [x.close for x in candles[:idx+1]]
        volumes = [x.volume for x in candles[:idx+1]]
        highs = [x.high for x in candles[:idx+1]]
        lows = [x.low for x in candles[:idx+1]]

        ta = {}
        # RSI (14)
        if len(closes) >= 15:
            gains = [max(closes[i]-closes[i-1], 0) for i in range(-14, 0)]
            losses = [max(closes[i-1]-closes[i], 0) for i in range(-14, 0)]
            avg_gain = sum(gains)/14
            avg_loss = sum(losses)/14
            rs = (avg_gain / avg_loss) if avg_loss > 0 else 999
            ta["rsi"] = 100 - (100 / (1 + rs))
        else:
            ta["rsi"] = 50

        # EMAs
        for period, key in [(9, "ema_9"), (21, "ema_21"), (50, "ema_50")]:
            if len(closes) >= period:
                k = 2 / (period + 1)
                ema = closes[-period]
                for price in closes[-(period-1):]:
                    ema = price * k + ema * (1 - k)
                ta[key] = ema
            else:
                ta[key] = c.close

        # MACD
        if len(closes) >= 26:
            k12, k26 = 2/13, 2/27
            ema12 = sum(closes[-12:])/12 if len(closes) < 12 else closes[-12]
            ema26 = sum(closes[-26:])/26
            for price in closes[-(min(26, len(closes))-1):]:
                ema12 = price * k12 + ema12 * (1 - k12)
                ema26 = price * k26 + ema26 * (1 - k26)
            ta["macd"] = ema12 - ema26
            # Signal line (9-period EMA of MACD)
            if len(closes) >= 35:
                sig = ta["macd"]
                count = 0
                ta["macd_signal"] = sig  # simplified
            else:
                ta["macd_signal"] = 0
            ta["macd_histogram"] = ta.get("macd", 0) - ta.get("macd_signal", 0)
        else:
            ta["macd"] = ta["macd_signal"] = ta["macd_histogram"] = 0

        # Bollinger Bands (20,2)
        if len(closes) >= 20:
            window = closes[-20:]
            mean = sum(window)/20
            variance = sum((p-mean)**2 for p in window)/20
            std = variance ** 0.5
            ta["bb_upper"] = mean + 2*std
            ta["bb_mid"] = mean
            ta["bb_lower"] = mean - 2*std
        else:
            ta["bb_upper"] = c.close * 1.02
            ta["bb_mid"] = c.close
            ta["bb_lower"] = c.close * 0.98

        # ATR (14)
        if len(highs) >= 15 and len(lows) >= 15:
            trs = []
            for i in range(-14, 0):
                hl = highs[i] - lows[i]
                hc = abs(highs[i] - closes[i-1])
                lc = abs(lows[i] - closes[i-1])
                trs.append(max(hl, hc, lc))
            ta["atr"] = sum(trs)/14
        else:
            ta["atr"] = (c.high - c.low) * 0.5

        ta["volume_ratio"] = c.volume / (sum(volumes[-20:])/20) if len(volumes) >= 20 else 1
        ta["adx"] = 25  # simplified

        return ta

    def _run_agents(self, symbol: str, candle: Candle, md: dict,
                    analysts: list, bullish_res, bearish_res,
                    trader, risk_mgr, port_mgr) -> Optional[dict]:
        """Run the V7 pipeline — trader decides, risk/PM for info only."""
        try:
            # 1. Analysts (parallel)
            reports = []
            with ThreadPoolExecutor(4) as pool:
                futures = [pool.submit(a.analyze, symbol, md) for a in analysts]
                for f in as_completed(futures):
                    reports.append(f.result())

            # 2. Researchers (parallel)
            with ThreadPoolExecutor(2) as pool:
                fb = pool.submit(bullish_res.analyze, symbol, md, reports)
                fbe = pool.submit(bearish_res.analyze, symbol, md, reports)
                bull_report = fb.result()
                bear_report = fbe.result()

            # 3. Trader decides (primary signal)
            portfolio = {"balance": self.balance, "available": self.balance,
                        "margin": 0, "positions": len(self.open_trades),
                        "daily_pnl": 0}
            td = trader.decide(symbol, md, reports, [bull_report, bear_report], portfolio)

            if not td or td.direction == "NEUTRAL" or td.confidence < 0.3:
                return None

            size = td.key_metrics.get("size_pct", 0.1)
            if size <= 0:
                return None

            dt = candle.datetime.strftime("%Y-%m-%d %H:%M")
            print(f"  [{dt}] V7:{td.direction} ${candle.close:.0f} "
                  f"conf={td.confidence:.2f} size={size*100:.0f}%")

            return {
                "direction": td.direction,
                "confidence": td.confidence,
                "size_pct": size,
                "sl_pct": 2.5,
                "tp_pct": 5.0,
                "agent_used": "V7",
            }
        except Exception as e:
            print(f"  ⚠️ Agent pipeline error: {e}")
            return None

    def _check_trades(self, candle: Candle):
        """Check open trades against SL/TP/expiry."""
        still_open = []
        for t in self.open_trades:
            hit = False
            if t.direction == "LONG":
                if candle.low <= t.entry_price * (1 - t.sl_pct/100):
                    # SL hit
                    sl_price = t.entry_price * (1 - t.sl_pct/100)
                    t.exit_price = sl_price
                    t.exit_reason = "SL"
                    t.pnl_pct = -t.sl_pct
                    hit = True
                elif candle.high >= t.entry_price * (1 + t.tp_pct/100):
                    tp_price = t.entry_price * (1 + t.tp_pct/100)
                    t.exit_price = tp_price
                    t.exit_reason = "TP"
                    t.pnl_pct = t.tp_pct
                    hit = True
            else:  # SHORT
                if candle.high >= t.entry_price * (1 + t.sl_pct/100):
                    sl_price = t.entry_price * (1 + t.sl_pct/100)
                    t.exit_price = sl_price
                    t.exit_reason = "SL"
                    t.pnl_pct = -t.sl_pct
                    hit = True
                elif candle.low <= t.entry_price * (1 - t.tp_pct/100):
                    tp_price = t.entry_price * (1 - t.tp_pct/100)
                    t.exit_price = tp_price
                    t.exit_reason = "TP"
                    t.pnl_pct = t.tp_pct
                    hit = True

            if hit:
                t.exit_time = candle.time
                t.pnl_usd = self.initial_balance * t.size_pct * t.pnl_pct / 100
                self.balance += self.initial_balance * t.size_pct + t.pnl_usd
                self.trades.append(t)
            else:
                still_open.append(t)

        # Update unrealized P&L for still-open trades
        for t in still_open:
            if t.direction == "LONG":
                t.pnl_pct = (candle.close / t.entry_price - 1) * 100
            else:
                t.pnl_pct = (t.entry_price / candle.close - 1) * 100

        self.open_trades = still_open

    def _open_trade(self, signal: dict, candle: Candle):
        """Open a new trade from a signal."""
        trade = BacktestTrade(
            symbol="BTCUSD",
            direction=signal["direction"],
            entry_time=candle.time,
            entry_price=candle.close,
            size_pct=signal["size_pct"],
            sl_pct=signal["sl_pct"],
            tp_pct=signal["tp_pct"],
            confidence=signal["confidence"],
        )
        margin = self.initial_balance * signal["size_pct"]
        if margin < 1 or margin > self.balance:
            return
        self.balance -= margin
        self.open_trades.append(trade)

    def _record_equity(self, candle: Candle):
        """Record equity curve point."""
        total_margin = sum(self.initial_balance * t.size_pct for t in self.open_trades)
        unrealized = sum(
            self.initial_balance * t.size_pct * (
                (candle.close / t.entry_price - 1) if t.direction == "LONG"
                else (t.entry_price / candle.close - 1)
            )
            for t in self.open_trades
        )
        self.equity = self.balance + total_margin + unrealized
        self.equity_curve.append({
            "time": candle.time,
            "equity": self.equity,
            "balance": self.balance,
            "price": candle.close,
            "open_trades": len(self.open_trades),
        })

    def _close_remaining(self, last_candle: Candle):
        """Close any trades still open at end of backtest."""
        for t in self.open_trades:
            t.exit_time = last_candle.time
            t.exit_price = last_candle.close
            t.exit_reason = "expiry"
            if t.direction == "LONG":
                t.pnl_pct = (t.exit_price / t.entry_price - 1) * 100
            else:
                t.pnl_pct = (t.entry_price / t.exit_price - 1) * 100
            t.pnl_usd = self.initial_balance * t.size_pct * t.pnl_pct / 100
            self.trades.append(t)
        self.open_trades = []

    def check_openai_credits(self) -> bool:
        """Test if OpenAI/OpenRouter credits are available."""
        import requests
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            return False
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={"model": "openai/gpt-4o-mini",
                      "messages": [{"role": "user", "content": "test"}],
                      "max_tokens": 5},
                headers={"Authorization": f"Bearer {key}"},
                timeout=5
            )
            return r.status_code == 200
        except:
            return False

    def run(self, symbol: str = "BTCUSD", resolution: str = "4h",
            lookback_days: int = 365, tick_interval: int = 4) -> dict:
        """Run the full V7 AI backtest."""
        print(f"\n{'='*55}")
        print(f"  V7 AI BACKTEST — {symbol} ({resolution})")
        print(f"  Initial Balance: ${self.initial_balance:.2f}")
        print(f"  Ticks: every {tick_interval} candle(s)")
        print(f"{'='*55}")

        loader = HistoricalDataLoader(symbol)
        candles = loader.fetch(resolution, lookback_days)
        print(f"  Loaded {len(candles)} candles from "
              f"{candles[0].datetime.date()} to {candles[-1].datetime.date()}")

        warmup = 100  # Need enough candles for technicals
        if len(candles) <= warmup:
            raise RuntimeError(f"Not enough data: {len(candles)} candles")

        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.trades = []
        self.open_trades = []
        self.equity_curve = []
        self.tick_count = 0

        start_idx = warmup
        last_progress_pct = 0

        # Create agents once and reuse
        print("  Initializing V7 agents...")
        analysts = [FundamentalsAnalyst(), SentimentAnalyst(),
                    NewsAnalyst(), TechnicalAnalyst()]
        bullish_res = BullishResearcher()
        bearish_res = BearishResearcher()
        trader = TraderAgent()
        risk_mgr = RiskManager()
        port_mgr = PortfolioManager()
        print("  Done.")

        for idx in range(start_idx, len(candles)):
            candle = candles[idx]
            self.tick_count += 1

            # Progress
            pct = ((idx - start_idx) / (len(candles) - start_idx)) * 100
            if pct - last_progress_pct >= 5:
                trades_closed = len([t for t in self.trades if t.exit_reason != "open"])
                print(f"  ⏳ {pct:.0f}% — {trades_closed} closed, {len(self.open_trades)} open "
                      f"| Eq=${self.equity:.0f}")
                last_progress_pct = pct

            # Check open trades
            self._check_trades(candle)

            # Only analyze at tick intervals
            if (idx - start_idx) % tick_interval != 0:
                self._record_equity(candle)
                continue

            # Build market data with real technicals
            ta = self.compute_technicals(candles, idx)
            md = {
                "price": candle.close,
                "volume_24h": candle.volume * 24 * 3600,
                "high_24h": candle.high,
                "low_24h": candle.low,
                "change_24h": candle.return_pct,
                "funding_rate": 0.01,
                "open_interest": 0,
                "volatility_24h": (candle.high - candle.low) / candle.close * 100,
                "technical": ta,
                "regime": "trending" if ta["ema_9"] > ta["ema_21"] else "ranging",
                "news_headlines": [],
                "news_global": [],
                "social_sentiment": "neutral",
                "fear_greed": 50,
                "macro_events": {},
            }

            signal = self._run_agents(symbol, candle, md, analysts,
                                       bullish_res, bearish_res,
                                       trader, risk_mgr, port_mgr)
            if signal:
                self._open_trade(signal, candle)

            self._record_equity(candle)

        # Close remaining
        self._close_remaining(candles[-1])
        return self._report()

    def _report(self) -> dict:
        """Generate performance report."""
        total_return = self.equity - self.initial_balance
        total_return_pct = (self.equity / self.initial_balance - 1) * 100

        total_trades = len([t for t in self.trades if t.exit_reason != "open"])
        winning_trades = [t for t in self.trades if t.pnl_usd > 0]
        losing_trades = [t for t in self.trades if t.pnl_usd <= 0]
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0

        avg_win = sum(t.pnl_usd for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(abs(t.pnl_usd) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')

        # Max drawdown
        peak = self.initial_balance
        max_dd = 0
        for e in self.equity_curve:
            if e["equity"] > peak:
                peak = e["equity"]
            dd = (peak - e["equity"]) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (annualized, 4h candles)
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                r = (self.equity_curve[i]["equity"] / self.equity_curve[i-1]["equity"] - 1)
                returns.append(r)
            avg_ret = sum(returns) / len(returns) if returns else 0
            std_ret = (sum((r - avg_ret)**2 for r in returns) / len(returns)) ** 0.5 if returns else 1
            # Annualize: 4h candles -> 2190 per year
            sharpe = (avg_ret / std_ret) * (2190 ** 0.5) if std_ret > 0 else 0
        else:
            sharpe = 0

        # Trade details
        trade_log = []
        for t in self.trades:
            if t.exit_reason != "open":
                entry_dt = datetime.fromtimestamp(t.entry_time, tz=timezone.utc)
                exit_dt = datetime.fromtimestamp(t.exit_time, tz=timezone.utc)
                trade_log.append({
                    "direction": t.direction,
                    "entry": entry_dt.strftime("%Y-%m-%d %H:%M"),
                    "entry_price": t.entry_price,
                    "exit": exit_dt.strftime("%Y-%m-%d %H:%M"),
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "pnl_pct": round(t.pnl_pct, 2),
                    "pnl_usd": round(t.pnl_usd, 2),
                    "confidence": t.confidence,
                })

        report = {
            "symbol": "BTCUSD",
            "period": f"{self.equity_curve[0]['time'] if self.equity_curve else '?'} — "
                      f"{self.equity_curve[-1]['time'] if self.equity_curve else '?'}",
            "initial_balance": self.initial_balance,
            "final_equity": round(self.equity, 2),
            "total_return": round(total_return_pct, 2),
            "total_return_usd": round(total_return, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "open_trades": len(self.open_trades),
            "trade_log": trade_log,
        }
        return report

    def print_report(self, report: dict):
        """Pretty-print the backtest report."""
        print(f"\n{'='*55}")
        print(f"  V7 AI BACKTEST RESULTS")
        print(f"{'='*55}")
        print(f"  Period: {report['period']}")
        print(f"  Starting Capital: ${report['initial_balance']:.2f}")
        print(f"  Final Equity:     ${report['final_equity']:.2f}")
        print(f"  Total Return:     {report['total_return']:+.2f}% "
              f"(${report['total_return_usd']:+.2f})")
        print(f"  Total Trades:     {report['total_trades']}")
        print(f"  Win Rate:         {report['win_rate']}%")
        print(f"  Profit Factor:    {report['profit_factor']}")
        print(f"  Max Drawdown:     {report['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe Ratio:     {report['sharpe_ratio']}")
        print(f"  Avg Win:          ${report['avg_win_usd']:.2f}")
        print(f"  Avg Loss:         ${report['avg_loss_usd']:.2f}")
        print(f"  Winning Trades:   {report['winning_trades']}")
        print(f"  Losing Trades:    {report['losing_trades']}")
        print(f"{'='*55}\n")

        if report["trade_log"]:
            print("  TRADE LOG (last 20):")
            print(f"  {'Dir':<6} {'Entry':<20} {'Price':<8} {'Exit':<20} {'Price':<8} {'By':<10} {'P&L':<8}")
            print(f"  {'-'*80}")
            for t in report["trade_log"][-20:]:
                label = f"{t['pnl_pct']:+.2f}%"
                print(f"  {t['direction']:<6} {t['entry']:<20} ${t['entry_price']:<6.0f} "
                      f"{t['exit']:<20} ${t['exit_price']:<6.0f} "
                      f"{t['exit_reason']:<10} {label:<8}")
