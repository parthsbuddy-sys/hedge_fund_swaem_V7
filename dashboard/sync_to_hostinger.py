"""
V7 Hedge Fund — Hostinger Sync Uploader
Runs alongside the engine and pushes live status to your Hostinger domain.

Usage:
  python sync_to_hostinger.py --url https://darkgreen-trout-572733.hostingersite.com/trading/sync.php --secret your-secret

Or set env vars:
  HOSTINGER_SYNC_URL=https://.../sync.php
  HOSTINGER_SYNC_SECRET=your-secret

Then run in background:
  python sync_to_hostinger.py --daemon --interval 10
"""

import os, sys, json, time, requests, signal
from pathlib import Path

BASE = Path(__file__).parent.parent
STATUS_FILE = BASE / "live_status.json"
KEYS_FILE = BASE / "dashboard" / "api_keys.json"
PID_FILE = BASE / "dashboard" / ".sync.pid"

# ── Config ────────────────────────────────────────────────────

SYNC_URL = os.getenv("HOSTINGER_SYNC_URL", "")
SYNC_SECRET = os.getenv("HOSTINGER_SYNC_SECRET", "change-this-secret")
INTERVAL = int(os.getenv("HOSTINGER_SYNC_INTERVAL", "10"))

# ── Helpers ────────────────────────────────────────────────────

def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

def sync_once():
    status = read_json(STATUS_FILE) or {"engine": "OFFLINE", "balance": 0}
    keys = read_json(KEYS_FILE) or []
    
    payload = {
        "status": status,
        "keys": keys,
        "engine": status.get("engine", "OFFLINE"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    
    try:
        resp = requests.post(
            SYNC_URL,
            json=payload,
            headers={
                "X-Sync-Secret": SYNC_SECRET,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return True, resp.text
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, str(e)

def daemon_loop():
    print(f"  🔄 Hostinger sync daemon started")
    print(f"  📡 URL: {SYNC_URL}")
    print(f"  ⏱️  Interval: {INTERVAL}s")
    print(f"  Press Ctrl+C to stop\n")
    
    # Write PID
    with open(PID_FILE, "w") as f:
        json.dump({"pid": os.getpid(), "started": time.time()}, f)
    
    running = True
    
    def handle_signal(sig, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    while running:
        ok, msg = sync_once()
        ts = time.strftime("%H:%M:%S")
        status_icon = "✅" if ok else "❌"
        print(f"  {status_icon} [{ts}] {msg if ok else msg}")
        
        for _ in range(INTERVAL):
            if not running:
                break
            time.sleep(1)
    
    # Cleanup
    if PID_FILE.exists():
        PID_FILE.unlink()
    print("  ⏹️  Sync daemon stopped")

# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="V7 Hostinger Sync Uploader")
    parser.add_argument("--url", help="Sync endpoint URL (or HOSTINGER_SYNC_URL env)")
    parser.add_argument("--secret", help="Sync secret (or HOSTINGER_SYNC_SECRET env)")
    parser.add_argument("--interval", type=int, default=INTERVAL, help="Sync interval in seconds")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in foreground")
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    
    args = parser.parse_args()
    
    if args.url:
        SYNC_URL = args.url
    if args.secret:
        SYNC_SECRET = args.secret
    if args.interval:
        INTERVAL = args.interval
    
    if not SYNC_URL:
        print("❌ No sync URL set. Use --url or HOSTINGER_SYNC_URL env var.")
        sys.exit(1)
    
    if args.daemon:
        daemon_loop()
    elif args.once:
        ok, msg = sync_once()
        print(f"{'✅' if ok else '❌'} {msg}")
    else:
        ok, msg = sync_once()
        print(f"{'✅' if ok else '❌'} Sync: {msg}")
        print("Tip: Use --daemon to run continuously, or --once for a single sync.")
