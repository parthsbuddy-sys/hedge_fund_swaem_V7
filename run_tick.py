import os, sys
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, os.getcwd())

from core.orchestrator import HedgeFundSwarmV7

engine = HedgeFundSwarmV7()
print("V7 HEDGE FUND SWARM — SINGLE TICK", flush=True)
engine.run_tick()
print("\n✅ Tick complete", flush=True)
