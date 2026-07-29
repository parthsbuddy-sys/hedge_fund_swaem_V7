"""Test full V7 agent pipeline with NVIDIA NIM (free)."""
import os, sys, time
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, os.getcwd())

from concurrent.futures import ThreadPoolExecutor, as_completed
from agents.analyst_team import (
    FundamentalsAnalyst, SentimentAnalyst, NewsAnalyst, TechnicalAnalyst
)
from agents.researcher_team import BullishResearcher, BearishResearcher
from agents.trader import TraderAgent
from agents.risk_manager import RiskManager
from agents.portfolio_manager import PortfolioManager

# BTCUSD market data as of now
md = {
    "price": 65860.73,
    "volume_24h": 1250000000.0,
    "high_24h": 67000.0,
    "low_24h": 64800.0,
    "change_24h": 2.5,
    "funding_rate": 0.01,
    "open_interest": 28500000000.0,
    "volatility_24h": 3.2,
    "technical": {
        "rsi": 58.3,
        "macd_histogram": 120.5,
        "bb_upper": 67800.0,
        "bb_mid": 65600.0,
        "bb_lower": 63400.0,
        "ema_9": 66100.0,
        "ema_21": 65200.0,
    },
    "regime": "trending",
    "news_headlines": ["Fed holds rates, crypto rallies"],
    "news_global": ["BTC ETF inflows $300M"],
    "social_sentiment": "slightly bullish",
    "fear_greed": 62,
    "macro_events": {},
}
portfolio = {"balance": 576.89, "available": 576.89, "margin": 0,
             "positions": 0, "daily_pnl": 0}

symbol = "BTCUSD"
t0 = time.time()

# 1. Analysts (4 parallel)
analysts = [FundamentalsAnalyst(), SentimentAnalyst(),
            NewsAnalyst(), TechnicalAnalyst()]
reports = []
with ThreadPoolExecutor(4) as pool:
    for f in as_completed([pool.submit(a.analyze, symbol, md) for a in analysts]):
        reports.append(f.result())
print(f"Analysts done in {time.time()-t0:.1f}s")
for r in reports:
    print(f"  [{r.agent_name}] {r.direction} (conf={r.confidence:.2f})")

# 2. Researchers (2 parallel)
bullish = BullishResearcher()
bearish = BearishResearcher()
with ThreadPoolExecutor(2) as pool:
    fb = pool.submit(bullish.analyze, symbol, md, reports)
    fbe = pool.submit(bearish.analyze, symbol, md, reports)
    bull_report = fb.result()
    bear_report = fbe.result()
print(f"Researchers done in {time.time()-t0:.1f}s")
print(f"  [Bullish] {bull_report.direction} (conf={bull_report.confidence:.2f})")
print(f"  [Bearish] {bear_report.direction} (conf={bear_report.confidence:.2f})")

# 3. Trader (decision)
trader = TraderAgent()
td = trader.decide(symbol, md, reports, [bull_report, bear_report], portfolio)
print(f"Trader done in {time.time()-t0:.1f}s")
print(f"  [Trader] {td.direction} (conf={td.confidence:.2f} size={td.key_metrics.get('size_pct',0)*100:.0f}%)")

# 4. Risk Manager
risk = RiskManager()
rr = risk.assess(symbol, md, td, portfolio)
print(f"Risk done in {time.time()-t0:.1f}s")
print(f"  [Risk] approved={rr.key_metrics.get('approved')}")

# 5. Portfolio Manager
pm = PortfolioManager()
pdr = pm.approve(symbol, md, td, rr, portfolio)
print(f"PM done in {time.time()-t0:.1f}s")
print(f"  [PM] approved={pdr.key_metrics.get('approved')}")
print(f"  Final: {pdr.direction} size={pdr.key_metrics.get('final_size',0)*100:.0f}%")

print(f"\nTotal pipeline: {time.time()-t0:.1f}s")
