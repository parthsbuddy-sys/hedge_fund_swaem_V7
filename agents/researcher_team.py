"""V7 Researcher Team — Bullish & Bearish debate analysts."""
from .base_agent import BaseAgent, AgentReport

class BullishResearcher(BaseAgent):
    def __init__(self):
        super().__init__("Bullish Researcher")

    def analyze(self, symbol: str, market_data: dict,
                analyst_reports: list) -> AgentReport:
        reports_str = "\n".join(
            f"[{r.agent_name}] {r.direction} conf={r.confidence:.2f}"
            for r in analyst_reports)
        sp = "You output ONLY one line: DIRECTION:LONG/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"Build BULLISH case for {symbol}\n{reports_str}"
        text = self._call_llm(sp, up)
        dec = self._parse_decision(text)
        if dec["direction"] not in ("LONG", "SHORT"):
            dec["direction"] = "LONG"
        return AgentReport(self.name, symbol, dec["direction"], dec["confidence"],
                           text, dec["reasoning"], dec["risk"], {})


class BearishResearcher(BaseAgent):
    def __init__(self):
        super().__init__("Bearish Researcher")

    def analyze(self, symbol: str, market_data: dict,
                analyst_reports: list) -> AgentReport:
        reports_str = "\n".join(
            f"[{r.agent_name}] {r.direction} conf={r.confidence:.2f}"
            for r in analyst_reports)
        sp = "You output ONLY one line: DIRECTION:SHORT/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"Build BEARISH case for {symbol}\n{reports_str}"
        text = self._call_llm(sp, up)
        dec = self._parse_decision(text)
        if dec["direction"] not in ("LONG", "SHORT"):
            dec["direction"] = "SHORT"
        return AgentReport(self.name, symbol, dec["direction"], dec["confidence"],
                           text, dec["reasoning"], dec["risk"], {})
