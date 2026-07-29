"""V7 Risk Manager — VaR, Kelly sizing, volatility assessment."""
from .base_agent import BaseAgent, AgentReport

class RiskManager(BaseAgent):
    """Portfolio-level risk assessment and position sizing."""

    def __init__(self):
        super().__init__("Risk Manager")

    def assess(self, symbol: str, market_data: dict,
               trader_decision: AgentReport,
               portfolio_state: dict) -> AgentReport:
        """Evaluate risk of the proposed trade."""

        price = market_data.get("price", 0)
        volatility = market_data.get("volatility_24h", 0)
        balance = portfolio_state.get("balance", 0)
        available = portfolio_state.get("available", 0)
        positions = portfolio_state.get("positions", 0)
        daily_pnl = portfolio_state.get("daily_pnl", 0)

        sp = """You are the CHIEF RISK OFFICER at a professional hedge fund.
Your job: PROTECT CAPITAL. Evaluate the proposed trade for:
1. Position size risk — is it within Kelly criterion bounds?
2. Market volatility — is entry safe given current vol ({vol:.2f}%)?
3. Portfolio concentration — are we overexposed?
4. Stop-loss adequacy — does SL protect against gap risk?
5. Correlation risk — any related positions open?

Output JSON:
{
  "approved": true/false,
  "max_size_pct": 0.0-1.0,
  "adjusted_stop_pct": 0.0-5.0,
  "adjusted_tp_pct": 0.0-20.0,
  "reason": "risk rationale"
}"""

        up = f"""Asset: {symbol} | Price: ${price:.2f} | 24h Vol: {volatility:.2f}%
Proposed: {trader_decision.direction} size={trader_decision.key_metrics.get('size_pct',0)*100:.1f}%
Stop: {trader_decision.key_metrics.get('stop_loss_pct',2):.1f}% | TP: {trader_decision.key_metrics.get('take_profit_pct',4):.1f}%

Portfolio: Balance=${balance:.2f} | Available=${available:.2f} | Positions={positions} | Daily P&L=${daily_pnl:.2f}

Risk assessment (JSON only):"""

        text = self._call_llm(sp, up, temperature=0.1)

        import re, json
        json_match = re.search(r'\{[^{}]*\}', text)
        approved = True
        max_size = trader_decision.key_metrics.get("size_pct", 0.05)
        adj_sl = trader_decision.key_metrics.get("stop_loss_pct", 2.0)
        adj_tp = trader_decision.key_metrics.get("take_profit_pct", 4.0)
        reason = text[:300]

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                approved = parsed.get("approved", True)
                max_size = min(1.0, float(parsed.get("max_size_pct", max_size)))
                adj_sl = float(parsed.get("adjusted_stop_pct", adj_sl))
                adj_tp = float(parsed.get("adjusted_tp_pct", adj_tp))
                reason = parsed.get("reason", reason)
            except:
                pass

        direction = "CASH"
        conf = 0.5
        if approved:
            direction = trader_decision.direction
            conf = min(1.0, trader_decision.confidence * 0.85)

        return AgentReport(
            self.name, symbol, direction, conf,
            text, reason, 1.0 - conf,
            {"approved": approved, "max_size_pct": max_size,
             "adjusted_sl": adj_sl, "adjusted_tp": adj_tp, "daily_pnl": daily_pnl}
        )
