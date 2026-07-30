"""V7 Configuration — all settings in one place."""
import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class V7Config:
    # Trading
    symbols: List[str] = field(default_factory=lambda: ["BTCUSD", "ETHUSD", "SOLUSD"])
    tick_interval: int = 60  # seconds (LLM analysis takes time)
    max_trades_per_tick: int = 2
    max_portfolio_risk_pct: float = 2.0  # max % risk per trade

    # LLM
    llm_provider: str = "openrouter"
    llm_model: str = field(default_factory=lambda: os.getenv("V7_LLM_MODEL", "moonshotai/kimi-k2.6"))
    temperature: float = 0.15
    reasoning_model: str = field(default_factory=lambda: os.getenv("V7_REASONING_MODEL", "moonshotai/kimi-k2.6"))

    # Risk
    kelly_fraction: float = 0.25
    max_daily_drawdown_pct: float = 5.0
    correlation_same_asset_limit: int = 1

    # Delta
    exchange: str = "delta"
    base_url: str = field(default_factory=lambda: os.getenv("DELTA_BASE_URL", "https://cdn.deltaex.org"))

    # Paths
    memory_path: str = "memory"
    log_dir: str = "logs"
    data_dir: str = "."

    @classmethod
    def from_env(cls):
        return cls(
            symbols=os.getenv("V7_SYMBOLS", "BTCUSD,ETHUSD,SOLUSD").split(","),
            tick_interval=int(os.getenv("V7_TICK_INTERVAL", "10")),
            temperature=float(os.getenv("V7_TEMPERATURE", "0.15")),
        )
