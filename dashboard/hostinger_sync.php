<?php
/**
 * V7 Hedge Fund — Hostinger Live Sync Endpoint
 * 
 * Upload this file to your Hostinger server.
 * It receives live engine status + API keys and serves the dashboard.
 *
 * INSTALL:
 * 1. Upload this file to https://darkgreen-trout-572733.hostingersite.com/trading/sync.php
 * 2. Set a sync secret below
 * 3. Run the local sync script (sync_to_hostinger.py) or use the dashboard's sync panel
 */

// ── CONFIG ─────────────────────────────────────────────────
$SYNC_SECRET = "change-this-secret";  // Set same secret in your local sync script
$DATA_DIR = __DIR__ . "/data";         // Where status/keys JSON files are stored
// ────────────────────────────────────────────────────────────

// Ensure data directory exists
if (!is_dir($DATA_DIR)) {
    mkdir($DATA_DIR, 0755, true);
}

$method = $_SERVER['REQUEST_METHOD'];
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$basename = basename($path);

// ── CORS headers ──
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, X-Sync-Secret");
if ($method === "OPTIONS") {
    http_response_code(204);
    exit;
}

// ── POST: Receive sync data from engine ──
if ($method === "POST") {
    // Verify secret
    $secret = $_SERVER['HTTP_X_SYNC_SECRET'] ?? '';
    if ($secret !== $SYNC_SECRET) {
        http_response_code(403);
        die("Invalid sync secret");
    }
    
    $input = json_decode(file_get_contents("php://input"), true);
    if (!$input) {
        http_response_code(400);
        die("Invalid JSON");
    }
    
    // Save status
    if (isset($input['status'])) {
        file_put_contents("$DATA_DIR/status.json", json_encode($input['status'], JSON_PRETTY_PRINT));
    }
    
    // Save keys (read-only — keys are managed locally, synced here for display)
    if (isset($input['keys'])) {
        file_put_contents("$DATA_DIR/keys.json", json_encode($input['keys'], JSON_PRETTY_PRINT));
    }
    
    // Save engine state
    file_put_contents("$DATA_DIR/last_sync.txt", date("Y-m-d H:i:s") . " UTC");
    
    echo "OK";
    exit;
}

// ── GET: Serve data or dashboard HTML ──

// API endpoints
if ($path === "/trading/api/status" || $path === "/trading/status.json") {
    header("Content-Type: application/json");
    $f = "$DATA_DIR/status.json";
    echo file_exists($f) ? file_get_contents($f) : '{"engine":"OFFLINE"}';
    exit;
}

if ($path === "/trading/api/keys" || $path === "/trading/keys.json") {
    header("Content-Type: application/json");
    $f = "$DATA_DIR/keys.json";
    echo file_exists($f) ? file_get_contents($f) : '[]';
    exit;
}

// Serve the dashboard HTML
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V7 Hedge Fund — Live</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0b0e;color:#e2e8f0;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1b2e,#0d0e14);border-bottom:1px solid #2d2d3a;padding:14px 20px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:18px;background:linear-gradient(90deg,#818cf8,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.status-bar{display:flex;align-items:center;gap:8px;padding:10px 20px;border-bottom:1px solid #1e1f2b;font-size:13px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.dot.green{background:#22c55e;box-shadow:0 0 8px #22c55e88}
.dot.red{background:#ef4444;box-shadow:0 0 8px #ef444488}
.dot.yellow{background:#eab308;box-shadow:0 0 8px #eab30888}
.pane{padding:16px 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px}
.card{background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:14px}
.card .lbl{font-size:10px;text-transform:uppercase;color:#6b7280;letter-spacing:.5px;margin-bottom:3px}
.card .val{font-size:20px;font-weight:600}
.card .sub{font-size:11px;color:#6b7280;margin-top:2px}
.card.green .val{color:#22c55e}.card.red .val{color:#ef4444}.card.purple .val{color:#818cf8}.card.blue .val{color:#60a5fa}.card.orange .val{color:#f59e0b}
h2{font-size:13px;color:#9ca3af;margin-bottom:8px}
.pos-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
.pos-card{background:#12131a;border:1px solid #1e1f2b;border-radius:10px;padding:12px}
.pos-card .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.pos-card .sym{font-weight:600;font-size:14px}
.pos-card .side{font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600}
.side.SHORT{background:#3b1a1a;color:#ef4444}.side.LONG{background:#1a3b1a;color:#22c55e}
.pos-card .row{display:flex;justify-content:space-between;font-size:12px;color:#9ca3af;padding:2px 0}
.pos-card .pnl{font-weight:600;font-size:13px}
.pnl.pos{color:#22c55e}.pnl.neg{color:#ef4444}
.footer{text-align:center;padding:14px;font-size:11px;color:#4b5563;border-top:1px solid #1e1f2b}
.last-sync{font-size:11px;color:#6b7280;margin-top:8px}
.empty{color:#6b7280;text-align:center;padding:20px;font-size:13px}
</style>
</head>
<body>
<div class="header">
  <h1>🦊 V7 Hedge Fund — Live</h1>
  <span style="font-size:11px;color:#6b7280" id="lastSync">syncing...</span>
</div>
<div class="status-bar">
  <span class="dot red" id="statusDot"></span>
  <span id="statusText">OFFLINE</span>
  <span style="margin-left:auto;font-size:11px;color:#6b7280" id="refreshText"></span>
</div>
<div class="pane">
  <div class="grid" id="summaryCards"></div>
  <h2>📊 Open Positions</h2>
  <div class="pos-grid" id="positionsContainer"></div>
</div>
<div class="footer">V7 Hedge Fund Swarm — Data refreshes every 5s</div>

<script>
async function refresh(){
  try {
    const r=await fetch('status.json?_t='+Date.now());
    const d=await r.json();
    
    const dot=document.getElementById('statusDot');
    const txt=document.getElementById('statusText');
    if(d.engine==='RUNNING'){dot.className='dot green';txt.textContent='RUNNING'}
    else if(d.engine==='OFFLINE'){dot.className='dot red';txt.textContent='OFFLINE'}
    else{dot.className='dot yellow';txt.textContent=d.engine}
    
    document.getElementById('refreshText').textContent=new Date().toLocaleTimeString();
    document.getElementById('lastSync').textContent=d.timestamp||'—';
    
    document.getElementById('summaryCards').innerHTML=`
      <div class="card purple"><div class="lbl">Balance</div><div class="val">$${(d.balance||0).toFixed(2)}</div><div class="sub">Available: $${(d.available||0).toFixed(2)}</div></div>
      <div class="card ${d.positions>0?'green':'blue'}"><div class="lbl">Open Positions</div><div class="val">${d.positions||0}</div></div>
      <div class="card orange"><div class="lbl">Trades</div><div class="val">${d.trades_opened||0}</div></div>
      <div class="card ${(d.win_rate||0)>=50?'green':'red'}"><div class="lbl">Win Rate</div><div class="val">${d.win_rate||0}%</div></div>
      <div class="card blue"><div class="lbl">Tick</div><div class="val">${d.tick_time||0}s</div></div>
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
      pc.innerHTML='<div class="empty">No open positions</div>';
    }
  } catch(e){
    document.getElementById('refreshText').textContent='⚠️ offline';
  }
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
