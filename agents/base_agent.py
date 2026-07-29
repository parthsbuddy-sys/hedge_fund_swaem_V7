"""Base LLM Agent for V7 Hedge Fund Swarm."""
import os, json, time, logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class LLMProvider(str, Enum):
    DECISION = "meta/llama-3.1-8b-instruct"     # Quality (free NVIDIA NIM)
    FAST = "meta/llama-3.1-8b-instruct"         # Fast (free NVIDIA NIM)


_NIM_MODEL_PREFIXES = ["meta/", "mistralai/", "microsoft/", "google/"]


@dataclass
class AgentReport:
    agent_name: str
    symbol: str
    direction: Optional[str]  # LONG / SHORT / NEUTRAL
    confidence: float          # 0.0 - 1.0
    analysis: str
    reasoning: str
    risk_score: float          # 0.0 (safe) - 1.0 (very risky)
    key_metrics: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class BaseAgent:
    """Professional hedge fund agent — LLM-driven analysis."""

    def __init__(self, name: str, model: str = None):
        self.name = name
        self.model = model or os.getenv("V7_LLM_MODEL", LLMProvider.FAST.value)
        self.max_retries = 3
        self.temperature = float(os.getenv("V7_TEMPERATURE", "0.15"))
        self.timeout = int(os.getenv("V7_LLM_TIMEOUT", "60"))

        # NVIDIA NIM models use different API key + base URL
        self._is_nim = any(self.model.startswith(p) for p in _NIM_MODEL_PREFIXES)
        if self._is_nim:
            self.api_key = os.getenv(
                "NVIDIA_NIM_API_KEY",
                "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"
            )
            self.base_url = "https://integrate.api.nvidia.com/v1"
        else:
            self.api_key = os.getenv("OPENROUTER_API_KEY", "")
            self.base_url = os.getenv("OPENROUTER_BASE_URL",
                                      "https://openrouter.ai/api/v1")

    def _call_llm(self, system_prompt: str, user_prompt: str,
                  temperature: float = None) -> str:
        """Call LLM with retry logic. Routes to NVIDIA NIM or OpenRouter."""
        if not self.api_key:
            logger.warning(f"[{self.name}] No API key configured")
            return ""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if not self._is_nim:
            # OpenRouter needs referer
            headers["HTTP-Referer"] = "https://v7-hedge-fund.local"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": 256,
        }

        for attempt in range(self.max_retries):
            try:
                import requests
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("choices", [{}])[0].get("message", {})
                    content = msg.get("content") or msg.get("reasoning") or ""
                    return content
                elif resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"[{self.name}] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"[{self.name}] LLM error {resp.status_code}: "
                                 f"{resp.text[:200]}")
                    if attempt < self.max_retries - 1:
                        time.sleep(1)
                        continue
                    return ""
            except Exception as e:
                logger.error(f"[{self.name}] LLM call failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                    continue
                return ""
        return ""

    def _parse_decision(self, text: str) -> dict:
        """Parse LLM output into structured decision. Handles ONE-LINE format."""
        direction = "NEUTRAL"
        confidence = 0.0
        risk = 0.5
        reasoning = (text or "")[:500]

        text_clean = (text or "").lower()

        import re
        dir_match = re.search(r'direction[\:\s]+(\w+)', text_clean)
        if dir_match:
            d = dir_match.group(1).upper()
            if d in ("LONG", "SHORT", "NEUTRAL", "CASH"):
                direction = d
            elif d in ("BULLISH", "BULL"):
                direction = "LONG"
            elif d in ("BEARISH", "BEAR"):
                direction = "SHORT"

        conf_match = re.search(r'confidence[\:\s]+([\d.]+)', text_clean)
        if conf_match:
            confidence = float(conf_match.group(1))
        conf_match = re.search(r'(\d+)\%\s*confidence', text_clean)
        if conf_match:
            confidence = float(conf_match.group(1)) / 100.0
        confidence = max(0.0, min(1.0, confidence))

        risk_match = re.search(r'risk[\:\s]+([\d.]+)', text_clean)
        if risk_match:
            risk = float(risk_match.group(1))
        risk = max(0.0, min(1.0, risk))

        return {"direction": direction, "confidence": confidence,
                "risk": risk, "reasoning": reasoning, "metrics": {}}

    def analyze(self, symbol: str, market_data: dict) -> AgentReport:
        """Run analysis. Override in subclasses."""
        raise NotImplementedError

    def _report(self, symbol: str, text: str) -> AgentReport:
        """Build an AgentReport from LLM output."""
        d = self._parse_decision(text)
        return AgentReport(self.name, symbol, d["direction"], d["confidence"],
                           text, d["reasoning"], d["risk"], {})
