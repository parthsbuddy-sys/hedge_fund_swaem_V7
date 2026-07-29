"""V7 Analyst Team — Fundamentals, Sentiment, News, Technical Analysts."""
import os, json, re
from .base_agent import BaseAgent, AgentReport

class FundamentalsAnalyst(BaseAgent):
    def __init__(self):
        super().__init__("Fundamentals Analyst")

    def analyze(self, symbol: str, market_data: dict) -> AgentReport:
        price = market_data.get("price", 0)
        volume = market_data.get("volume_24h", 0)
        funding = market_data.get("funding_rate", 0)
        oi = market_data.get("open_interest", 0)
        sp = "You output ONLY one line: DIRECTION:LONG or SHORT or NEUTRAL/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"{symbol} Price=${price:.0f} Vol=${volume:.0f} Funding={funding:.6f} OI=${oi:.0f}"
        return self._report(symbol, self._call_llm(sp, up))


class SentimentAnalyst(BaseAgent):
    def __init__(self):
        super().__init__("Sentiment Analyst")

    def analyze(self, symbol: str, market_data: dict) -> AgentReport:
        fg = market_data.get("fear_greed", 50)
        sp = "You output ONLY one line: DIRECTION:LONG or SHORT or NEUTRAL/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"{symbol} FearGreed={fg}"
        return self._report(symbol, self._call_llm(sp, up))


class NewsAnalyst(BaseAgent):
    def __init__(self):
        super().__init__("News Analyst")

    def analyze(self, symbol: str, market_data: dict) -> AgentReport:
        news = str(market_data.get("news_global", ""))[:300]
        sp = "You output ONLY one line: DIRECTION:LONG or SHORT or NEUTRAL/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"{symbol} News={news}"
        return self._report(symbol, self._call_llm(sp, up))


class TechnicalAnalyst(BaseAgent):
    def __init__(self):
        super().__init__("Technical Analyst")

    def analyze(self, symbol: str, market_data: dict) -> AgentReport:
        ta = market_data.get("technical", {})
        rsi = ta.get("rsi", 50)
        macd = ta.get("macd_histogram", 0)
        cross = "bullish" if ta.get("ema_9", 0) > ta.get("ema_21", 0) else "bearish"
        sp = "You output ONLY one line: DIRECTION:LONG or SHORT or NEUTRAL/CONFIDENCE:0.0-1.0/RISK:0.0-1.0"
        up = f"{symbol} RSI={rsi:.0f} MACD={macd:.4f} EMA={cross}"
        return self._report(symbol, self._call_llm(sp, up))
