"""V7 Backtest — Run the real V7 AI multi-agent pipeline on historical data."""
import os, sys
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)

from dotenv import load_dotenv
load_dotenv(os.path.join(root, '.env'))

from backtest.engine import BacktestEngine

print("V7 HEDGE FUND SWARM — AI BACKTEST")
print("=" * 55)
print()

engine = BacktestEngine(initial_balance=576.89)

# 4h candles, evaluate every 4th candle (~every 16h in backtest time)
# tick_interval=4 means ~300 ticks instead of 1276
report = engine.run(
    symbol="BTCUSD",
    resolution="4h",
    lookback_days=365,
    tick_interval=8,  # every ~1.3 days → ~147 ticks, fast + meaningful
)

# Save report
log_dir = os.path.join(root, "logs")
os.makedirs(log_dir, exist_ok=True)
report_path = os.path.join(log_dir, "backtest_report.json")
import json
with open(report_path, "w") as f:
    json.dump(report, f, indent=2, default=str)

print(f"\nReport saved to: {report_path}")

# Print summary
engine.print_report(report)
