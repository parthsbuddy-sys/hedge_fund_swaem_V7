"""V7 Hedge Fund Swarm — Entry Point"""
import os, sys, json
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# Force LIVE mode — this is criminal
os.environ.setdefault("ENGINE_MODE", "LIVE")

# Reduce LLM logging noise
import logging
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

from config.settings import V7Config
from core.orchestrator import HedgeFundSwarmV7

if __name__ == "__main__":
    # Start live dashboard (uses Railway PORT env or defaults to 8081)
    try:
        from dashboard.app import start_dashboard
        dashboard_port = int(os.environ.get("PORT", "8081"))
        start_dashboard(port=dashboard_port)
    except Exception as e:
        print(f"  ⚠️  Dashboard not started: {e}")
    print("""
 ██╗   ██╗███████╗    ██╗  ██╗███████╗██████╗  ██████╗ ███████╗
 ██║   ██║██╔════╝    ██║  ██║██╔════╝██╔══██╗██╔════╝ ██╔════╝
 ██║   ██║███████╗    ███████║█████╗  ██║  ██║██║  ███╗█████╗  
 ╚██╗ ██╔╝╚════██║    ██╔══██║██╔══╝  ██║  ██║██║   ██║██╔══╝  
  ╚████╔╝ ███████║    ██║  ██║███████╗██████╔╝╚██████╔╝███████╗
   ╚═══╝  ╚══════╝    ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝
        HEDGE FUND SWARM — Multi-Agent Institutional AI
    """)

    config = V7Config.from_env()
    swarm = HedgeFundSwarmV7(config)

    # Check wallets
    from execution import DeltaBroker
    broker1 = DeltaBroker(account=1)
    broker2 = DeltaBroker(account=2)
    try:
        w1 = broker1.get_wallet()
    except Exception as e:
        print(f"  ⚠️  Acc#1 wallet check failed: {e}")
        w1 = {"balance": 0, "available": 0}
    try:
        w2 = broker2.get_wallet()
    except Exception as e:
        print(f"  ⚠️  Acc#2 wallet check failed: {e}")
        w2 = {"balance": 0, "available": 0}
    print(f"  💰 Acc#1: ${w1.get('balance',0):.2f} (Avail: ${w1.get('available',0):.2f})")
    print(f"  💰 Acc#2: ${w2.get('balance',0):.2f} (Avail: ${w2.get('available',0):.2f})")

    if w1.get("balance", 0) < 5 and w2.get("balance", 0) < 5:
        print("  ⚠️  Both accounts low — running in paper-observation mode")
    else:
        print(f"  ✅ Trading capital available")

    for i, b in enumerate([broker1, broker2], 1):
        try:
            positions = b.get_positions()
        except Exception as e:
            print(f"  ⚠️  Acc#{i} positions check failed: {e}")
            continue
        if positions:
            print(f"  📋 Acc#{i} open positions: {len(positions)}")
            for p in positions[:2]:
                print(f"     {p['symbol']} size={p['size']:.4f} P&L=${p['pnl']:.2f}")

    print()
    swarm.run()
