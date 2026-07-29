"""V7 Orchestrator — multi-agent hedge fund main loop."""
import os, sys, time, json, logging
from datetime import datetime
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import V7Config
from core.memory import DecisionMemory
from data.market_data import MarketDataProvider
from execution import DeltaBroker, TradeSetup, OrderSide, OrderStatus, OrderType

from agents.analyst_team import (
    FundamentalsAnalyst, SentimentAnalyst,
    NewsAnalyst, TechnicalAnalyst
)
from agents.researcher_team import BullishResearcher, BearishResearcher
from agents.trader import TraderAgent
from agents.risk_manager import RiskManager
from agents.portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)

class HedgeFundSwarmV7:
    """Professional multi-agent AI hedge fund — V7."""

    def __init__(self, config: Optional[V7Config] = None):
        self.config = config or V7Config.from_env()
        self.running = False
        self.tick_count = 0

        # Data & Broker
        self.data_provider = MarketDataProvider()
        self.brokers = [
            DeltaBroker(account=1),  # Primary account
            DeltaBroker(account=2),  # Second account
        ]
        self.memory = DecisionMemory()

        # Agents
        self.analysts = [
            FundamentalsAnalyst(),
            SentimentAnalyst(),
            NewsAnalyst(),
            TechnicalAnalyst(),
        ]
        self.bullish_researcher = BullishResearcher()
        self.bearish_researcher = BearishResearcher()
        self.trader = TraderAgent()
        self.risk_manager = RiskManager()
        self.portfolio_manager = PortfolioManager()

        self._setup_logging()

    def _setup_logging(self):
        os.makedirs(self.config.log_dir, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        fh = logging.FileHandler(os.path.join(self.config.log_dir, "v7.log"))
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        logger.setLevel(logging.INFO)

    def _print_banner(self):
        print(f"""
╔══════════════════════════════════════════════╗
║      HERMES V7 — HEDGE FUND SWARM            ║
║      Multi-Agent AI Institutional Trading    ║
║      Symbols: {', '.join(self.config.symbols):36s}║
║      LLM: {self.config.llm_model:42s}║
║      Mode: {'LIVE' if os.getenv('ENGINE_MODE','LIVE') == 'LIVE' else 'PAPER'}                         ║
╚══════════════════════════════════════════════╝
        """)

    def get_portfolio_state(self) -> dict:
        wallet = self.brokers[0].get_wallet()
        positions = self.brokers[0].get_positions()
        # Also check account #2
        wallet2 = self.brokers[1].get_wallet()
        return {
            "balance": wallet.get("balance", 0),
            "available": wallet.get("available", 0),
            "margin": wallet.get("margin", 0),
            "positions": len(positions),
            "open_positions": positions,
            "daily_pnl": sum(p.get("pnl", 0) for p in positions),
            "balance_2": wallet2.get("balance", 0),
            "available_2": wallet2.get("available", 0),
        }

    def check_risk(self, portfolio: dict) -> bool:
        """Risk check - closes losing positions if drawdown exceeds threshold.
        Returns True if it's safe to trade, False if positions were force-closed."""
        try:
            # Check positions on both accounts
            total_pnl = 0.0
            total_balance = portfolio.get("balance", 0)

            for acc in [1, 2]:
                broker = self.get_portfolio_broker(acc)
                positions = broker.get_positions()
                if not positions:
                    continue
                for p in positions:
                    pnl = float(p.get("pnl", 0))
                    total_pnl += pnl

                # If any single position exceeds 10% loss, close it
                for p in positions:
                    pnl = float(p.get("pnl", 0))
                    margin = float(p.get("margin", 1))
                    pnl_pct = (pnl / margin) * 100 if margin > 0 else 0
                    sym = p.get("symbol", p.get("product_symbol", "?"))
                    sz = float(p["size"])
                    direction = "LONG" if sz > 0 else "SHORT"
                    if pnl_pct <= -10:
                        print(f"  🛑 STOP LOSS: {direction} {sym} P&L={pnl_pct:.1f}% (exceeds -10%)")
                        broker.close_position(sym)
                        print(f"    ✅ Closed {direction} {sym}")

            # Total account drawdown check
            if total_balance > 0:
                dd_pct = (total_pnl / total_balance) * 100
                print(f"  📊 Portfolio drawdown: {dd_pct:.1f}% (${total_pnl:.2f})")
                if dd_pct <= -15:
                    print(f"  🛑 MAX DRAWDOWN: {dd_pct:.1f}% — closing ALL positions!")
                    for acc in [1, 2]:
                        try:
                            self.get_portfolio_broker(acc).close_all_positions()
                        except:
                            pass
                    return False  # not safe to trade
            return True
        except Exception as e:
            print(f"  ⚠️  Risk check error: {e}")
            return True

    def get_portfolio_broker(self, account: int = 1) -> 'DeltaBroker':
        """Get broker for specific account."""
        for b in self.brokers:
            if b.account == account:
                return b
        return self.brokers[0]

    def run_tick(self):
        """Execute one full trading tick with parallel agent calls."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        self.tick_count += 1
        start_time = time.time()
        print(f"\n{'='*55}")
        print(f"  TICK #{self.tick_count} — {datetime.utcnow().strftime('%H:%M:%S')} UTC")
        print(f"{'='*55}")

        portfolio = self.get_portfolio_state()
        print(f"  💰 Balance=${portfolio['balance']:.2f}  Avail=${portfolio['available']:.2f}  "
              f"Positions={portfolio['positions']}  P&L=${portfolio['daily_pnl']:.2f}")

        # ⚡ RISK CHECK — stop loss / drawdown management
        safe_to_trade = self.check_risk(portfolio)
        if not safe_to_trade:
            print(f"  ⏸️  Risk limit hit — skipping this tick")
            print(f"  ⏱️  Tick done in {time.time()-start_time:.1f}s | Trades opened: 0")
            print(f"  📈 Historical win rate: {self.memory.win_rate:.1f}%")
            print(f"\n  ⏳ Waiting {tick_interval}s until next tick...")
            time.sleep(tick_interval)
            return

        trades_opened = 0
        all_reports = []

        for symbol in self.config.symbols:
            if trades_opened >= self.config.max_trades_per_tick:
                break

            print(f"\n  ── Analyzing {symbol} ──")

            # 1. Fetch market data
            market_data = self.data_provider.get_market_data(symbol)
            price = market_data.get("price", 0)
            print(f"  📊 Price=${price:.2f}  Vol={market_data.get('volatility_24h',0):.2f}%  "
                  f"RSI={market_data.get('technical',{}).get('rsi',50):.1f}")

            # 2. Analyst Team — PARALLEL
            print(f"  👥 Analysts running (4 in parallel)...")
            analyst_reports = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                fut = {pool.submit(a.analyze, symbol, market_data): a for a in self.analysts}
                for f in as_completed(fut):
                    a = fut[f]
                    try:
                        report = f.result(timeout=60)
                        analyst_reports.append(report)
                        print(f"    [{report.agent_name}] {report.direction} "
                              f"(conf={report.confidence:.2f}, risk={report.risk_score:.2f})")
                    except Exception as e:
                        logger.error(f"    ❌ {a.name} failed: {e}")

            # 3. Researcher Team — PARALLEL debate
            print(f"  🗣️  Research Debate (2 in parallel)...")
            bull_report = bear_report = None
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_bull = pool.submit(self.bullish_researcher.analyze, symbol, market_data, analyst_reports)
                fut_bear = pool.submit(self.bearish_researcher.analyze, symbol, market_data, analyst_reports)
                try: bull_report = fut_bull.result(timeout=60); print(f"    [Bullish] {bull_report.direction} (conf={bull_report.confidence:.2f})")
                except Exception as e: logger.error(f"    ❌ Bullish failed: {e}")
                try: bear_report = fut_bear.result(timeout=60); print(f"    [Bearish] {bear_report.direction} (conf={bear_report.confidence:.2f})")
                except Exception as e: logger.error(f"    ❌ Bearish failed: {e}")

            if not bull_report or not bear_report:
                print(f"  ⚠️  Research debate incomplete, skipping")
                continue

            # 4. Trader — synthesize (DeepSeek)
            print(f"  🎯 Trader deciding...")
            try:
                trader_decision = self.trader.decide(
                    symbol, market_data, analyst_reports,
                    [bull_report, bear_report],
                    portfolio_state=portfolio
                )
                print(f"    [Trader] {trader_decision.direction} "
                      f"(conf={trader_decision.confidence:.2f}, "
                      f"size={trader_decision.key_metrics.get('size_pct',0)*100:.1f}%)")
            except Exception as e:
                logger.error(f"  ❌ Trader failed: {e}")
                continue

            # Skip if no clear direction
            if trader_decision.direction in ("CASH", "NEUTRAL") or trader_decision.confidence < 0.3:
                print(f"  💤 No trade signal ({trader_decision.direction} / low confidence)")
                continue

            # Determine trade size — integer contracts
            # Delta BTCUSD: 1 contract = 0.001 BTC = ~$65 at $65K
            trader_size = trader_decision.key_metrics.get("size_pct", 0.1)
            if trader_size <= 0:
                print(f"  💤 Size too small")
                continue

            final_dir = trader_decision.direction
            final_size = trader_size

            dt = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"  🎯 TRADE SIGNAL: {final_dir} conf={trader_decision.confidence:.2f} size={final_size*100:.0f}%")

            # 5. EXECUTE — place the trade (bypass risk/PM for quick deployment)
            print(f"  🚀 Executing trade...")
            try:
                side = OrderSide.BUY if final_dir == "LONG" else OrderSide.SELL
                available = portfolio.get("available", 0)
                size_value = available * final_size
                # Delta contract specs: BTCUSD=0.001 BTC/ct, ETHUSD=~0.001 ETH/ct
                # Compute integer contracts using 0.001 multiplier as baseline
                contract_val = price * 0.001 if symbol.startswith("BTC") else price * 0.001
                quant = max(1, int(size_value / contract_val)) if contract_val > 0 else 1
                # Cap at safe % of balance (margin)
                max_cap = int(available * 1.5 / contract_val) if contract_val > 0 else 1
                quant = min(quant, max_cap)

                print(f"    Size: ${size_value:.0f} → {quant} contracts @ ${price:.0f} (${contract_val:.2f}/ct)")
                setup = TradeSetup(
                    symbol=symbol, side=side, quantity=quant,
                    order_type=OrderType.MARKET, price=price,
                    stop_loss=2.5,
                    take_profit=5.0,
                    reason=str(trader_decision.reasoning or "")[:200],
                    confidence=trader_decision.confidence,
                )
                order = self.get_portfolio_broker(1).place_order(setup)

                if order.status == OrderStatus.FILLED:
                    print(f"    ✅ Acc#1 FILLED: {final_dir} {symbol} size={quant:.4f} @ ${order.fill_price:.2f}")
                    trades_opened += 1

                    # Also mirror on account #2 if it has balance
                    try:
                        broker2 = self.get_portfolio_broker(2)
                        bal2 = portfolio.get("available_2", 0)
                        if isinstance(bal2, (int, float)) and bal2 >= 5:
                            q2 = max(1, int(quant * 0.5))  # smaller size for acc2
                            setup2 = TradeSetup(
                                symbol=symbol, side=side, quantity=q2,
                                order_type=OrderType.MARKET, price=price,
                                stop_loss=2.5, take_profit=5.0,
                                reason=str(trader_decision.reasoning or "")[:200],
                                confidence=trader_decision.confidence,
                            )
                            order2 = broker2.place_order(setup2)
                            s2 = "✅ FILLED" if order2.status == OrderStatus.FILLED else f"❌ {str(order2.error or '?')[:60]}"
                            print(f"      ↳ Acc#2 {s2}")
                        else:
                            print(f"      ↳ Acc#2 💤 insufficient balance (${bal2:.2f})")
                    except Exception as e2:
                        print(f"      ↳ Acc#2 ❌ {e2}")

                    # Record to memory
                    all_reports = [*analyst_reports, bull_report, bear_report,
                                   trader_decision]
                    self.memory.record_decision(symbol, final_dir, trader_decision.confidence,
                                                trader_decision.reasoning[:200], all_reports)
                elif order.status == OrderStatus.REJECTED:
                    print(f"    ❌ REJECTED: {order.error}")
                else:
                    print(f"    ⏳ {order.status.value}: qty={order.filled_quantity}/{order.quantity} id={order.order_id[:12] if order.order_id else '?'}")

            except Exception as e:
                logger.error(f"  ❌ Execution failed: {e}")

        elapsed = time.time() - start_time
        print(f"\n  ⏱️  Tick done in {elapsed:.1f}s | Trades opened: {trades_opened}")
        win_rate = self.memory.get_win_rate()
        print(f"  📈 Historical win rate: {win_rate*100:.1f}%")

        # Write live status for dashboard
        self._write_live_status(portfolio, trades_opened, elapsed, win_rate)

    def _write_live_status(self, portfolio: dict, trades: int, elapsed: float, win_rate: float):
        """Write live status JSON for the dashboard."""
        try:
            import json, os
            # Get positions for both accounts
            positions_data = []
            for acc in [1, 2]:
                try:
                    broker = self.get_portfolio_broker(acc)
                    for p in broker.get_positions():
                        positions_data.append({
                            "account": acc,
                            "symbol": p["symbol"],
                            "side": "LONG" if p["size"] > 0 else "SHORT",
                            "size": abs(p["size"]),
                            "entry": p["entry"],
                            "mark": p["mark"],
                            "pnl": p["pnl"],
                            "margin": p["margin"],
                        })
                except:
                    pass

            status = {
                "timestamp": time.strftime("%H:%M:%S UTC"),
                "engine": "RUNNING",
                "balance": portfolio.get("balance", 0),
                "available": portfolio.get("available", 0),
                "positions": len(positions_data),
                "trades_opened": trades,
                "tick_time": round(elapsed, 1),
                "win_rate": round(win_rate * 100, 1),
                "positions_list": positions_data,
                "trade_history": self._get_recent_trades(),
            }
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live_status.json")
            with open(path, "w") as f:
                json.dump(status, f)
        except Exception as e:
            print(f"  ⚠️  Status write error: {e}")

    def _get_recent_trades(self) -> list:
        """Fetch last 10 trade decisions from the memory database."""
        try:
            import sqlite3
            db_path = os.path.join(self.config.data_dir, "memory", "decisions.db")
            if not os.path.exists(db_path):
                return []
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 10")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            return [{"error": str(e)}]

    def run(self):
        """Main trading loop."""
        self._print_banner()
        self.running = True

        try:
            while self.running:
                self.run_tick()

                if not self.running:
                    break

                # Sleep until next tick
                wait = max(1, self.config.tick_interval)
                print(f"\n  ⏳ Waiting {wait}s until next tick...")
                for s in range(wait):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            print("\n\n  ⛔ Stopping V7 Hedge Fund...")
        finally:
            self.running = False
            print("  🏁 V7 Hedge Fund stopped.")

    def stop(self):
        self.running = False
