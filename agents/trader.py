"""V7 Trader Agent — Synthesizes all analysis into trading decisions."""
from typing import Optional
from .base_agent import BaseAgent, AgentReport, LLMProvider

class TraderAgent(BaseAgent):
    """Synthesizes Analyst + Researcher reports into a trading decision."""

    def __init__(self):
        super().__init__("Head Trader", model=LLMProvider.FAST.value)
        self.timeout = 15

    def decide(self, symbol: str, market_data: dict,
               analyst_reports: list,
               researcher_reports: list,
               portfolio_state: dict = None) -> AgentReport:
        """Make final trading decision based on all inputs."""

        reports_str = "\n".join(
            f"[{r.agent_name}] {r.direction} conf={r.confidence:.2f} risk={r.risk_score:.2f}"
            for r in (analyst_reports + researcher_reports) if r)

        balance = portfolio_state.get("balance", 0) if portfolio_state else 0
        available = portfolio_state.get("available", 0) if portfolio_state else 0
        positions = portfolio_state.get("positions", 0) if portfolio_state else 0

        sp = """You are the HEAD TRADER at a $100M crypto hedge fund. Synthesize all analysis and make the final call.
You output ONLY one line: DIRECTION:LONG or SHORT or NEUTRAL or CASH/CONFIDENCE:0.0-1.0/SIZE_PCT:0.01-0.30/RISK:0.0-1.0"""

        up = f"Asset:{symbol} Bal=${balance} Avail=${available} Pos={positions}\n{reports_str}"

        text = self._call_llm(sp, up, temperature=0.1)

        dec = self._parse_decision(text)
        import re
        size_match = re.search(r'size_pct[:\s]+([\d.]+)', text.lower())
        size_pct = float(size_match.group(1)) if size_match else 0.05
        size_pct = min(0.3, max(0.01, size_pct))

        return AgentReport(
            self.name, symbol, dec["direction"], dec["confidence"],
            text, dec["reasoning"], dec["risk"],
            {"size_pct": size_pct, "balance": balance, "available": available}
        )
