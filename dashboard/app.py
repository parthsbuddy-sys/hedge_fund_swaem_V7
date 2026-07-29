"""V7 Hedge Fund — Full Web Control Panel
Multi-account API key management + engine control + live dashboard + Hostinger sync."""

import os, json, threading, subprocess, time
from flask import Flask, jsonify, render_template_string, request

BASE = os.path.dirname(os.path.dirname(__file__))
STATUS_PATH = os.path.join(BASE, "live_status.json")
KEYS_PATH = os.path.join(BASE, "dashboard", "api_keys.json")
ENGINE_PID_FILE = os.path.join(BASE, "dashboard", ".engine.pid")

app = Flask(__name__)

# ── Data ──────────────────────────────────────────────────────

def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_status():
    s = read_json(STATUS_PATH, {"engine":"OFFLINE","balance":0,"available":0,"positions":0})
    # check if engine process is alive
    pid = read_json(ENGINE_PID_FILE, {}).get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            s["engine"] = "RUNNING"
        except:
            s["engine"] = "STOPPED"
    return s

def get_keys():
    return read_json(KEYS_PATH, [])

def save_keys(keys):
    write_json(KEYS_PATH, keys)

# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/status")
def api_status():
    return jsonify(get_status())

@app.route("/api/keys", methods=["GET"])
def api_list_keys():
    return jsonify(get_keys())

@app.route("/api/keys", methods=["POST"])
def api_add_key():
    data = request.get_json()
    if not data or not data.get("api_key") or not data.get("api_secret"):
        return jsonify({"error": "API key and secret required"}), 400
    keys = get_keys()
    # check duplicate
    for k in keys:
        if k["api_key"] == data["api_key"]:
            return jsonify({"error": "Key already exists"}), 409
    keys.append({
        "label": data.get("label", f"Account #{len(keys)+1}"),
        "api_key": data["api_key"],
        "api_secret": data["api_secret"],
        "base_url": data.get("base_url", "https://testnet.deltaex.org"),
        "enabled": True,
    })
    save_keys(keys)
    return jsonify({"ok": True, "keys": keys})

@app.route("/api/keys/<int:idx>", methods=["DELETE"])
def api_del_key(idx):
    keys = get_keys()
    if idx < 0 or idx >= len(keys):
        return jsonify({"error": "Invalid index"}), 404
    keys.pop(idx)
    save_keys(keys)
    return jsonify({"ok": True, "keys": keys})

@app.route("/api/keys/<int:idx>/toggle", methods=["POST"])
def api_toggle_key(idx):
    keys = get_keys()
    if idx < 0 or idx >= len(keys):
        return jsonify({"error": "Invalid index"}), 404
    keys[idx]["enabled"] = not keys[idx].get("enabled", True)
    save_keys(keys)
    return jsonify({"ok": True, "keys": keys})

@app.route("/api/engine/start", methods=["POST"])
def api_start():
    if is_engine_running():
        return jsonify({"error": "Engine already running"}), 409
    try:
        proc = subprocess.Popen(
            ["python", "run.py"],
            cwd=BASE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        write_json(ENGINE_PID_FILE, {"pid": proc.pid, "started": time.time()})
        return jsonify({"ok": True, "pid": proc.pid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/engine/stop", methods=["POST"])
def api_stop():
    pid_data = read_json(ENGINE_PID_FILE, {})
    pid = pid_data.get("pid")
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 9)
        except:
            pass
        write_json(ENGINE_PID_FILE, {})
    return jsonify({"ok": True})

@app.route("/api/engine/status")
def api_engine_status():
    return jsonify({"running": is_engine_running(), "pid": read_json(ENGINE_PID_FILE, {}).get("pid")})

def is_engine_running():
    pid = read_json(ENGINE_PID_FILE, {}).get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except:
        return False

@app.route("/api/sync", methods=["GET"])
def api_sync_data():
    """Returns ALL data for Hostinger sync pickup."""
    return jsonify({
        "engine": is_engine_running(),
        "status": get_status(),
        "keys": get_keys(),
    })

# ── HTML Template (full control panel) ────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V7 Hedge Fund — Control Panel</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0b0e;color:#e2e8f0;min-height:100vh}
  /* Nav */
  .nav{background:linear-gradient(135deg,#1a1b2e,#0d0e14);border-bottom:1px solid #2d2d3a;padding:12px 24px;display:flex;align-items:center;gap:24px}
  .nav h1{font-size:18px;background:linear-gradient(90deg,#818cf8,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .nav .tabs{display:flex;gap:4px;margin-left:auto}
  .nav .tabs button{background:transparent;border:1px solid transparent;color:#6b7280;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;transition:.2s}
  .nav .tabs button:hover{color:#e2e8f0;border-color:#2d2d3a}
  .nav .tabs button.active{background:#1e1f2b;color:#818cf8;border-color:#818cf838}
  .tab{display:none}
  .tab.active{display:block}
  /* Header status bar */
  .status-bar{display:flex;align-items:center;gap:8px;padding:10px 24px;border-bottom:1px solid #1e1f2b;font-size:13px}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  .dot.green{background:#22c55e;box-shadow:0 0 8px #22c55e88}
  .dot.red{background:#ef4444;box-shadow:0 0 8px #ef444488}
  .dot.yellow{background:#eab308;box-shadow:0 0 8px #eab30888}
  .pane{padding:20px 24px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:20px}
  .card{background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:14px}
  .card .lbl{font-size:10px;text-transform:uppercase;color:#6b7280;letter-spacing:.5px;margin-bottom:3px}
  .card .val{font-size:20px;font-weight:600}
  .card .sub{font-size:11px;color:#6b7280;margin-top:2px}
  .card.green .val{color:#22c55e}
  .card.red .val{color:#ef4444}
  .card.purple .val{color:#818cf8}
  .card.blue .val{color:#60a5fa}
  .card.orange .val{color:#f59e0b}
  /* Positions */
  .pos-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
  .pos-card{background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:13px}
  .pos-card .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
  .pos-card .sym{font-weight:600;font-size:14px}
  .pos-card .side{font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600}
  .side.SHORT{background:#3b1a1a;color:#ef4444}
  .side.LONG{background:#1a3b1a;color:#22c55e}
  .pos-card .row{display:flex;justify-content:space-between;font-size:12px;color:#9ca3af;padding:2px 0}
  .pos-card .pnl{font-weight:600;font-size:13px}
  .pnl.pos{color:#22c55e}.pnl.neg{color:#ef4444}
  /* Keys table */
  .keys-table{width:100%;border-collapse:collapse;font-size:13px}
  .keys-table th{text-align:left;color:#6b7280;font-size:10px;text-transform:uppercase;padding:8px 12px;border-bottom:1px solid #1e1f2b}
  .keys-table td{padding:8px 12px;border-bottom:1px solid #1e1f2b;font-family:monospace;font-size:12px}
  .keys-table .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;font-family:sans-serif}
  .badge.on{background:#1a3b1a;color:#22c55e}
  .badge.off{background:#3b1a1a;color:#ef4444}
  .btn{background:#1e1f2b;border:1px solid #2d2d3a;color:#e2e8f0;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;transition:.2s}
  .btn:hover{background:#2d2d3a}
  .btn.danger{color:#ef4444;border-color:#ef444438}
  .btn.danger:hover{background:#3b1a1a}
  .btn.primary{background:#818cf8;border-color:#818cf8;color:#0a0b0e;font-weight:600}
  .btn.primary:hover{background:#a78bfa}
  .btn.green{background:#22c55e;border-color:#22c55e;color:#0a0b0e;font-weight:600}
  .btn.green:hover{background:#4ade80}
  .btn.red{background:#ef4444;border-color:#ef4444;color:#0a0b0e;font-weight:600}
  .btn.sm{padding:4px 10px;font-size:11px}
  form.form{display:flex;flex-direction:column;gap:10px;max-width:500px}
  form.form label{font-size:12px;color:#6b7280}
  form.form input{background:#1e1f2b;border:1px solid #2d2d3a;border-radius:6px;padding:8px 12px;color:#e2e8f0;font-size:13px;font-family:monospace}
  form.form input:focus{outline:none;border-color:#818cf8}
  .engine-ctrls{display:flex;gap:10px;margin-top:16px}
  .footer{text-align:center;padding:14px;font-size:11px;color:#4b5563;border-top:1px solid #1e1f2b}
  .toast{position:fixed;bottom:20px;right:20px;background:#1a1b2e;border:1px solid #2d2d3a;border-radius:8px;padding:12px 18px;font-size:13px;display:none;z-index:999}
  .toast.show{display:block;animation:fadeOut 3s forwards}
  @keyframes fadeOut{0%{opacity:1}70%{opacity:1}100%{opacity:0}}
  .empty{color:#6b7280;text-align:center;padding:30px;font-size:14px}
  .engine-card{background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:20px;display:flex;flex-direction:column;gap:12px;max-width:500px}
  .engine-card .info{display:flex;justify-content:space-between;font-size:13px}
</style>
</head>
<body>

<div class="nav">
  <h1>🦊 V7 Hedge Fund</h1>
  <div class="tabs">
    <button class="active" onclick="switchTab('dashboard')">📊 Dashboard</button>
    <button onclick="switchTab('keys')">🔑 API Keys</button>
    <button onclick="switchTab('engine')">⚙️ Engine</button>
  </div>
</div>

<div class="status-bar">
  <span class="dot" id="statusDot"></span>
  <span id="statusText">Loading...</span>
  <span style="margin-left:auto;font-size:11px;color:#6b7280" id="refreshText"></span>
</div>

<!-- TAB: Dashboard -->
<div class="tab active" id="tab-dashboard">
  <div class="pane">
    <div class="grid" id="summaryCards"></div>
    <h2 style="font-size:13px;color:#9ca3af;margin-bottom:8px">📊 Open Positions</h2>
    <div class="pos-grid" id="positionsContainer"></div>
  </div>
</div>

<!-- TAB: API Keys -->
<div class="tab" id="tab-keys">
  <div class="pane">
    <h2 style="font-size:13px;color:#9ca3af;margin-bottom:12px">🔑 Delta Exchange API Keys</h2>
    <table class="keys-table" id="keysTable">
      <thead><tr><th>#</th><th>Label</th><th>API Key</th><th>Secret</th><th>Network</th><th>Status</th><th></th></tr></thead>
      <tbody id="keysBody"></tbody>
    </table>
    <div id="keysEmpty" class="empty">No API keys added yet</div>
    <details style="margin-top:16px">
      <summary style="color:#818cf8;cursor:pointer;font-size:13px">+ Add New API Key</summary>
      <form class="form" id="keyForm" style="margin-top:10px" onsubmit="addKey(event)">
        <div>
          <label>Label (e.g. Account #1)</label>
          <input type="text" name="label" placeholder="Personal Account" value="Account">
        </div>
        <div>
          <label>Delta API Key</label>
          <input type="text" name="api_key" placeholder="v8hv..." required>
        </div>
        <div>
          <label>Delta API Secret</label>
          <input type="text" name="api_secret" placeholder="0VGM..." required>
        </div>
        <div>
          <label>Network</label>
          <select name="base_url" style="background:#1e1f2b;border:1px solid #2d2d3a;border-radius:6px;padding:8px 12px;color:#e2e8f0;font-size:13px">
            <option value="https://testnet.deltaex.org">Testnet</option>
            <option value="https://cdn.deltaex.org">Mainnet</option>
          </select>
        </div>
        <button class="btn primary" type="submit">Save Key</button>
      </form>
    </details>
  </div>
</div>

<!-- TAB: Engine -->
<div class="tab" id="tab-engine">
  <div class="pane">
    <h2 style="font-size:13px;color:#9ca3af;margin-bottom:12px">⚙️ Engine Control</h2>
    <div class="engine-card">
      <div class="info"><span>Status</span><span id="engStatus">—</span></div>
      <div class="info"><span>PID</span><span id="engPid">—</span></div>
      <div class="info"><span>Last Tick</span><span id="engTick">—</span></div>
      <div class="engine-ctrls">
        <button class="btn green" onclick="engineStart()">▶ Start Engine</button>
        <button class="btn red" onclick="engineStop()">⏹ Stop Engine</button>
        <button class="btn" onclick="refreshAll()">🔄 Refresh</button>
      </div>
    </div>
    <h2 style="font-size:13px;color:#9ca3af;margin:16px 0 8px">🔗 Hostinger Sync</h2>
    <div style="background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:14px;font-size:13px;max-width:500px">
      <p style="color:#9ca3af;margin-bottom:8px">Upload current status to your Hostinger domain automatically.</p>
      <form onsubmit="syncHostinger(event)" style="display:flex;gap:8px;flex-wrap:wrap">
        <input type="url" name="sync_url" placeholder="https://yourdomain.com/sync.php" value="" style="background:#1e1f2b;border:1px solid #2d2d3a;border-radius:6px;padding:8px 12px;color:#e2e8f0;font-size:12px;flex:1;min-width:200px">
        <input type="password" name="sync_secret" placeholder="Sync secret" style="background:#1e1f2b;border:1px solid #2d2d3a;border-radius:6px;padding:8px 12px;color:#e2e8f0;font-size:12px;width:140px">
        <button class="btn primary" type="submit">Sync Now</button>
      </form>
      <div id="syncResult" style="margin-top:8px;font-size:12px;color:#6b7280"></div>
    </div>
  </div>
</div>

<div class="footer">V7 Hedge Fund Swarm — Multi-Agent Institutional AI</div>
<div class="toast" id="toast"></div>

<script>
// ── Tab switching ──
function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));
  document.querySelector(`.tabs button[onclick*="${name}"]`).classList.add('active');
  refreshAll();
}

// ── Toast ──
function toast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),3000);
}

// ── Fetch helpers ──
async function api(url,opts={}){
  const r=await fetch(url,{headers:{'Content-Type':'application/json'},...opts});
  return r.json();
}

// ── Dashboard refresh ──
async function loadDashboard(){
  const d=await api('/api/status');
  const dot=document.getElementById('statusDot');
  const txt=document.getElementById('statusText');
  if(d.engine==='RUNNING'){dot.className='dot green';txt.textContent='RUNNING'}
  else if(d.engine==='STOPPED'){dot.className='dot yellow';txt.textContent='STOPPED'}
  else{dot.className='dot red';txt.textContent='OFFLINE'}
  document.getElementById('refreshText').textContent=new Date().toLocaleTimeString();
  
  document.getElementById('summaryCards').innerHTML=`
    <div class="card purple"><div class="lbl">Balance</div><div class="val">$${(d.balance||0).toFixed(2)}</div><div class="sub">Available: $${(d.available||0).toFixed(2)}</div></div>
    <div class="card ${d.positions>0?'green':'blue'}"><div class="lbl">Open Positions</div><div class="val">${d.positions||0}</div></div>
    <div class="card orange"><div class="lbl">Trades This Tick</div><div class="val">${d.trades_opened||0}</div></div>
    <div class="card ${(d.win_rate||0)>=50?'green':'red'}"><div class="lbl">Win Rate</div><div class="val">${d.win_rate||0}%</div></div>
    <div class="card blue"><div class="lbl">Tick Time</div><div class="val">${d.tick_time||0}s</div></div>
  `;
  
  const pc=document.getElementById('positionsContainer');
  if(d.positions_list&&d.positions_list.length){
    pc.innerHTML=d.positions_list.map(p=>{
      const pc2=p.pnl>=0?'pos':'neg';
      const pp=p.margin>0?((p.pnl/p.margin)*100).toFixed(1):'0.0';
      return `<div class="pos-card">
        <div class="top"><span class="sym">#${p.account} ${p.symbol}</span><span class="side ${p.side}">${p.side}</span></div>
        <div class="row"><span>Size</span><span>${(p.size||0).toFixed(0)} cts</span></div>
        <div class="row"><span>Entry</span><span>$${(p.entry||0).toFixed(2)}</span></div>
        <div class="row"><span>Mark</span><span>$${(p.mark||0).toFixed(2)}</span></div>
        <div class="row"><span>P&L</span><span class="pnl ${pc2}">$${(p.pnl||0).toFixed(2)} (${pp}%)</span></div>
      </div>`;
    }).join('');
  }else{
    pc.innerHTML='<div class="empty" style="grid-column:1/-1">No open positions</div>';
  }
}

// ── API Keys tab ──
async function loadKeys(){
  const keys=await api('/api/keys');
  const tb=document.getElementById('keysBody');
  const empty=document.getElementById('keysEmpty');
  if(keys.length){
    empty.style.display='none';tb.innerHTML=keys.map((k,i)=>`
      <tr>
        <td>${i+1}</td>
        <td>${k.label||'Account'}</td>
        <td>${k.api_key.slice(0,12)}...</td>
        <td>${k.api_secret.slice(0,8)}...</td>
        <td>${k.base_url||'testnet'}</td>
        <td><span class="badge ${k.enabled?'on':'off'}">${k.enabled?'Active':'Disabled'}</span></td>
        <td>
          <button class="btn sm" onclick="toggleKey(${i})">${k.enabled?'Disable':'Enable'}</button>
          <button class="btn sm danger" onclick="delKey(${i})">Delete</button>
        </td>
      </tr>
    `).join('');
  }else{
    empty.style.display='block';tb.innerHTML='';
  }
}

async function addKey(e){
  e.preventDefault();
  const fd=new FormData(e.target);
  const body=Object.fromEntries(fd.entries());
  const r=await api('/api/keys',{method:'POST',body:JSON.stringify(body)});
  if(r.ok){toast('✅ Key added');loadKeys();e.target.reset()}
  else toast('❌ '+r.error);
}

async function delKey(i){
  if(!confirm('Delete key #'+(i+1)+'?'))return;
  const r=await api('/api/keys/'+i,{method:'DELETE'});
  if(r.ok){toast('🗑️ Key deleted');loadKeys()}
}

async function toggleKey(i){
  const r=await api('/api/keys/'+i+'/toggle',{method:'POST'});
  if(r.ok)loadKeys();
}

// ── Engine tab ──
async function loadEngine(){
  const s=await api('/api/engine/status');
  document.getElementById('engStatus').textContent=s.running?'🟢 RUNNING':'🔴 STOPPED';
  document.getElementById('engPid').textContent=s.pid||'—';
  const st=await api('/api/status');
  document.getElementById('engTick').textContent=st.timestamp||'—';
}

async function engineStart(){
  const r=await api('/api/engine/start',{method:'POST'});
  if(r.ok){toast('✅ Engine started (PID '+r.pid+')');loadEngine()}
  else toast('❌ '+r.error);
}

async function engineStop(){
  if(!confirm('Stop the engine? Open positions will remain open.'))return;
  const r=await api('/api/engine/stop',{method:'POST'});
  if(r.ok){toast('⏹️ Engine stopped');loadEngine()}
}

// ── Hostinger sync ──
async function syncHostinger(e){
  e.preventDefault();
  const fd=new FormData(e.target);
  const syncUrl=fd.get('sync_url');
  const secret=fd.get('sync_secret');
  if(!syncUrl){toast('❌ Enter sync URL');return}
  const data=await api('/api/sync');
  try{
    const r=await fetch(syncUrl,{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Sync-Secret':secret||''},
      body:JSON.stringify(data),
    });
    const res=await r.text();
    document.getElementById('syncResult').textContent=r.ok?'✅ Synced at '+new Date().toLocaleTimeString():'❌ HTTP '+r.status+': '+res.slice(0,100);
  }catch(e){
    document.getElementById('syncResult').textContent='❌ '+e.message;
  }
}

// ── Refresh all ──
async function refreshAll(){
  await Promise.all([loadDashboard(),loadKeys(),loadEngine()]);
}

// ── Init ──
refreshAll();
setInterval(loadDashboard,5000);
setInterval(loadEngine,10000);
</script>
</body>
</html>
"""

# ── Server ──

def run_dashboard(port=8081):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_dashboard(port=8081):
    t = threading.Thread(target=run_dashboard, args=(port,), daemon=True)
    t.start()
    print(f"  🌐 Dashboard: http://localhost:{port}")

if __name__ == "__main__":
    run_dashboard()
