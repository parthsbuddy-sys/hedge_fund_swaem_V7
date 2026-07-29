"""V7 Hedge Fund Live Dashboard — Web UI for real-time engine monitoring."""
import os, json, threading
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

STATUS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live_status.json")

def get_status():
    try:
        with open(STATUS_PATH) as f:
            return json.load(f)
    except:
        return {"engine": "OFFLINE", "balance": 0, "available": 0, "positions": 0}

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V7 Hedge Fund — Live Dashboard</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0a0b0e; color:#e2e8f0; min-height:100vh; }
  .header { background:linear-gradient(135deg,#1a1b2e,#0d0e14); border-bottom:1px solid #2d2d3a; padding:16px 24px; display:flex; align-items:center; justify-content:space-between; }
  .header h1 { font-size:20px; background:linear-gradient(90deg,#818cf8,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  .header .status { display:flex; align-items:center; gap:8px; font-size:13px; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
  .dot.green { background:#22c55e; box-shadow:0 0 8px #22c55e88; }
  .dot.red { background:#ef4444; box-shadow:0 0 8px #ef444488; }
  .dot.yellow { background:#eab308; box-shadow:0 0 8px #eab30888; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; padding:20px 24px; }
  .card { background:#12131a; border:1px solid #1e1f2b; border-radius:12px; padding:16px; }
  .card .label { font-size:11px; text-transform:uppercase; color:#6b7280; letter-spacing:.5px; margin-bottom:4px; }
  .card .value { font-size:22px; font-weight:600; }
  .card .sub { font-size:12px; color:#6b7280; margin-top:2px; }
  .card.green .value { color:#22c55e; }
  .card.red .value { color:#ef4444; }
  .card.purple .value { color:#818cf8; }
  .card.blue .value { color:#60a5fa; }
  .card.orange .value { color:#f59e0b; }
  h2 { font-size:14px; color:#9ca3af; padding:0 24px; margin-top:8px; margin-bottom:4px; text-transform:uppercase; letter-spacing:.5px; }
  .positions-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; padding:0 24px 24px; }
  .pos-card { background:#12131a; border:1px solid #1e1f2b; border-radius:10px; padding:14px; }
  .pos-card .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .pos-card .symbol { font-weight:600; font-size:15px; }
  .pos-card .side { font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600; }
  .side.SHORT { background:#3b1a1a; color:#ef4444; }
  .side.LONG { background:#1a3b1a; color:#22c55e; }
  .pos-card .detail { display:flex; justify-content:space-between; font-size:12px; color:#9ca3af; padding:3px 0; }
  .pos-card .pnl { font-weight:600; font-size:14px; }
  .pos-card .pnl.neg { color:#ef4444; }
  .pos-card .pnl.pos { color:#22c55e; }
  .footer { text-align:center; padding:16px; font-size:11px; color:#4b5563; border-top:1px solid #1e1f2b; margin-top:16px; }
  .refresh { font-size:11px; color:#6b7280; }
  .grid-wrap { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:0 24px; }
  .signal-card { background:#12131a; border:1px solid #1e1f2b; border-radius:10px; padding:12px; }
  .signal-card .title { font-size:11px; color:#6b7280; text-transform:uppercase; }
  .signal-card .sig { font-size:24px; font-weight:700; margin:4px 0; }
  .signal-card .sig.long { color:#22c55e; }
  .signal-card .sig.short { color:#ef4444; }
  .signal-card .sig.neutral { color:#eab308; }
  .bar { width:100%; height:6px; background:#1e1f2b; border-radius:3px; margin:4px 0; position:relative; overflow:hidden; }
  .bar .fill { height:100%; border-radius:3px; transition:width .5s; }
  .bar .fill.green { background:linear-gradient(90deg,#22c55e,#4ade80); }
  .bar .fill.red { background:linear-gradient(90deg,#ef4444,#f87171); }
  .bar .fill.yellow { background:linear-gradient(90deg,#eab308,#f59e0b); }
  @media(max-width:768px){ .grid-wrap{grid-template-columns:1fr;} }
</style>
</head>
<body>
<div class="header">
  <h1>🦊 V7 Hedge Fund</h1>
  <div class="status">
    <span id="statusDot" class="dot red"></span>
    <span id="statusText">OFFLINE</span>
    <span class="refresh" id="refreshText">—</span>
  </div>
</div>

<div class="grid" id="summaryCards"></div>

<h2>📊 Open Positions</h2>
<div class="positions-grid" id="positionsContainer"></div>

<h2>🤖 AI Signals (Last Tick)</h2>
<div class="grid-wrap" id="signalsContainer"></div>

<div class="footer">V7 Hedge Fund Swarm — Multi-Agent Institutional AI | <span id="tsLabel">waiting...</span></div>

<script>
async function refresh(){
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    
    // Status dot
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.engine === 'RUNNING'){ dot.className='dot green'; txt.textContent='RUNNING'; }
    else if(d.engine === 'OFFLINE'){ dot.className='dot red'; txt.textContent='OFFLINE'; }
    else { dot.className='dot yellow'; txt.textContent=d.engine; }
    
    // Summary cards
    document.getElementById('summaryCards').innerHTML = `
      <div class="card purple"><div class="label">Balance</div><div class="value">$${d.balance.toFixed(2)}</div><div class="sub">Available: $${d.available.toFixed(2)}</div></div>
      <div class="card ${d.positions > 0 ? 'green' : 'blue'}"><div class="label">Open Positions</div><div class="value">${d.positions}</div></div>
      <div class="card orange"><div class="label">Trades This Tick</div><div class="value">${d.trades_opened}</div></div>
      <div class="card ${d.win_rate >= 50 ? 'green' : 'red'}"><div class="label">Win Rate</div><div class="value">${d.win_rate}%</div></div>
      <div class="card blue"><div class="label">Tick Time</div><div class="value">${d.tick_time}s</div></div>
    `;
    
    // Positions
    const pc = document.getElementById('positionsContainer');
    if(d.positions_list && d.positions_list.length){
      pc.innerHTML = d.positions_list.map(p => {
        const pnlCls = p.pnl >= 0 ? 'pos' : 'neg';
        const pnlPct = p.margin > 0 ? ((p.pnl/p.margin)*100).toFixed(1) : '0.0';
        return `<div class="pos-card">
          <div class="top">
            <span class="symbol">#${p.account} ${p.symbol}</span>
            <span class="side ${p.side}">${p.side}</span>
          </div>
          <div class="detail"><span>Size</span><span>${p.size.toFixed(0)} cts</span></div>
          <div class="detail"><span>Entry</span><span>$${p.entry.toFixed(2)}</span></div>
          <div class="detail"><span>Mark</span><span>$${p.mark.toFixed(2)}</span></div>
          <div class="detail"><span>P&L</span><span class="pnl ${pnlCls}">$${p.pnl.toFixed(2)} (${pnlPct}%)</span></div>
        </div>`;
      }).join('');
    } else {
      pc.innerHTML = '<div class="pos-card" style="grid-column:1/-1;text-align:center;color:#6b7280;">No open positions</div>';
    }
    
    document.getElementById('tsLabel').textContent = d.timestamp || '—';
    document.getElementById('refreshText').textContent = 'updated ' + new Date().toLocaleTimeString();
  } catch(e){
    document.getElementById('refreshText').textContent = '⚠️ error';
  }
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/status")
def api_status():
    return jsonify(get_status())

def run_dashboard(port=8081):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_dashboard(port=8081):
    import threading
    t = threading.Thread(target=run_dashboard, args=(port,), daemon=True)
    t.start()
    print(f"  🌐 Dashboard: http://localhost:{port}")

if __name__ == "__main__":
    run_dashboard()
