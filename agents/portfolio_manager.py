"""V7 Portfolio Manager — Final approval authority."""
from .base_agent import BaseAgent, AgentReport

class PortfolioManager(BaseAgent):
    """Portfolio-level oversight — final approve/reject on all trades."""

    def __init__(self):
        super().__init__("Portfolio Manager")

    def approve(self, symbol: str, market_data: dict,
                trader_decision: AgentReport,
                risk_report: AgentReport,
                portfolio_state: dict) -> AgentReport:
        """Final gate — approve or reject the trade proposal."""

        sp = """You are the PORTFOLIO MANAGER of a $100M hedge fund.
Final authority on ALL trades. Consider:
1. Are we already overexposed to this asset/sector?
2. Does the risk-adjusted return meet our hurdle?
3. Any macro events that could invalidate the thesis?
4. Kelly-optimal position sizing
5. Daily drawdown limits

Output JSON:
{
  "approved": true/false,
  "final_direction": "LONG/SHORT/CASH",
  "final_size_pct": 0.0-1.0,
  "final_stop_pct": 0.0-5.0,
  "final_tp_pct": 0.0-20.0,
  "reason": "final decision rationale"
}"""

        balance = portfolio_state.get("balance", 0)
        available = portfolio_state.get("available", 0)
        daily_pnl = portfolio_state.get("daily_pnl", 0)

        up = f"""ASSET: {symbol} at ${market_data.get('price',0):.2f}

PROPOSAL: {trader_decision.direction}
Trader Confidence: {trader_decision.confidence:.2f}
Risk Score: {risk_report.risk_score:.2f}
Risk Approved: {risk_report.key_metrics.get('approved', False)}
Suggested Size: {trader_decision.key_metrics.get('size_pct',0)*100:.1f}% of capital
Risk-Adjusted SL: {risk_report.key_metrics.get('adjusted_sl',2):.1f}%
Risk-Adjusted TP: {risk_report.key_metrics.get('adjusted_tp',4):.1f}%

PORTFOLIO: Balance=${balance:.2f} | Available=${available:.2f} | Daily P&L=${daily_pnl:.2f}

Final decision (JSON only):"""

        text = self._call_llm(sp, up, temperature=0.15)

        import re, json
        json_match = re.search(r'\{[^{}]*\}', text)
        approved = False
        direction = "CASH"
        size = 0.0
        sl = 2.0
        tp = 4.0
        reason = text[:300]

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                approved = parsed.get("approved", False)
                direction = parsed.get("final_direction", "CASH")
                size = min(1.0, max(0.0, float(parsed.get("final_size_pct", 0.0))))
                sl = float(parsed.get("final_stop_pct", 2.0))
                tp = float(parsed.get("final_tp_pct", 4.0))
                reason = parsed.get("reason", reason)
            except:
                pass

        conf = trader_decision.confidence * (0.8 if approved else 0.3)
        return AgentReport(
            self.name, symbol, direction, conf,
            text, reason, 1.0 - conf,
            {"approved": approved, "final_size": size,
             "final_sl": sl, "final_tp": tp}
        )
