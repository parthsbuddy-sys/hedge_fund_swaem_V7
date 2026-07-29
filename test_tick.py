import os, sys, time, json
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, os.getcwd())

from execution import DeltaBroker
from data.market_data import MarketDataProvider
from agents.analyst_team import FundamentalsAnalyst, SentimentAnalyst, NewsAnalyst, TechnicalAnalyst
from agents.researcher_team import BullishResearcher, BearishResearcher
from agents.trader import TraderAgent
from agents.risk_manager import RiskManager
from agents.portfolio_manager import PortfolioManager
from concurrent.futures import ThreadPoolExecutor, as_completed

t_start = time.time()
broker = DeltaBroker()
wallet = broker.get_wallet()
data = MarketDataProvider()
s = 'BTCUSD'
md = data.get_market_data(s)
price = md['price']
print(f'BALANCE=${wallet["balance"]:.2f} | {s} @ ${price:.2f}')
sys.stdout.flush()

# Analysts parallel (as_completed for true parallelism)
analysts = [FundamentalsAnalyst(), SentimentAnalyst(), NewsAnalyst(), TechnicalAnalyst()]
analyst_reports = []
print('ANALYSTS...', end='', flush=True)
t0 = time.time()
with ThreadPoolExecutor(4) as pool:
    fut = {pool.submit(a.analyze, s, md): a for a in analysts}
    for f in as_completed(fut):
        try:
            r = f.result(90)
            analyst_reports.append(r)
            print(f' {r.agent_name}={r.direction}', end='', flush=True)
        except Exception as e:
            print(f' ERROR={e}', end='', flush=True)
t1 = time.time()
print(f' [{t1-t0:.1f}s]', flush=True)

# Researchers parallel
print('RESEARCH...', end='', flush=True)
t0 = time.time()
with ThreadPoolExecutor(2) as pool:
    fb = pool.submit(BullishResearcher().analyze, s, md, analyst_reports)
    fbe = pool.submit(BearishResearcher().analyze, s, md, analyst_reports)
    br = fb.result(90)
    ber = fbe.result(90)
t1 = time.time()
print(f' Bull={br.direction} Bear={ber.direction} [{t1-t0:.1f}s]', flush=True)

# Trader (uses KIMI - slow)
print('TRADER...', end='', flush=True)
t0 = time.time()
pf = dict(wallet) | {'positions': 0, 'open_positions': [], 'daily_pnl': 0}
td = TraderAgent().decide(s, md, analyst_reports, [br, ber], portfolio_state=pf)
t1 = time.time()
print(f' {td.direction} conf={td.confidence:.2f} [{t1-t0:.1f}s]', flush=True)

# Trader details
print(f'  Trader analysis: {td.reasoning[:200]}', flush=True)
print(f'  Size: {td.key_metrics.get("size_pct",0)*100:.1f}%', flush=True)

# Risk + PM (only if trade signal)
if td.direction not in ('CASH', 'NEUTRAL') and td.confidence >= 0.3:
    print('RISK...', end='', flush=True)
    t0 = time.time()
    rr = RiskManager().assess(s, md, td, pf)
    t1 = time.time()
    print(f' {"APPROVED" if rr.key_metrics.get("approved") else "DENIED"} [{t1-t0:.1f}s]', flush=True)
    print(f'  Risk analysis: {rr.reasoning[:200]}', flush=True)
    if rr.key_metrics.get('approved'):
        print('PM...', end='', flush=True)
        t0 = time.time()
        pdr = PortfolioManager().approve(s, md, td, rr, pf)
        t1 = time.time()
        print(f' {"APPROVED" if pdr.key_metrics.get("approved") else "DENIED"} {pdr.direction} [{t1-t0:.1f}s]', flush=True)
        print(f'  PM decision: {pdr.reasoning[:200]}', flush=True)
        if pdr.key_metrics.get('approved'):
            size = pdr.key_metrics.get('final_size', td.key_metrics.get('size_pct', 0))
            print(f'TRADE READY: {pdr.direction} {s} @ {size*100:.1f}% of capital', flush=True)
        else:
            print('PM DENIED trade', flush=True)
    else:
        print('Risk DENIED trade', flush=True)
else:
    print('NO TRADE SIGNAL - holding in cash', flush=True)

print(f'DURATION: {time.time()-t_start:.1f}s', flush=True)
