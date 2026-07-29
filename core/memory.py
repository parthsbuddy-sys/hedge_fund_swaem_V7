"""V7 Core — memory persistence, decision logging."""
import os, json, sqlite3
from datetime import datetime
from pathlib import Path

class DecisionMemory:
    """Persistent memory for trading decisions — cross-session learning."""

    def __init__(self):
        db_path = Path(os.getenv("V7_MEMORY_PATH", "memory/decisions.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                direction TEXT,
                confidence REAL,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                reason TEXT,
                agents_used TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER,
                agent_name TEXT,
                symbol TEXT,
                direction TEXT,
                confidence REAL,
                risk_score REAL,
                analysis TEXT,
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
            )
        """)
        self.conn.commit()

    def record_decision(self, symbol: str, direction: str, confidence: float,
                        reason: str, agents: list) -> int:
        cursor = self.conn.execute(
            "INSERT INTO decisions (timestamp, symbol, direction, confidence, entry_price, reason, agents_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), symbol, direction, confidence, 0.0, reason[:500], json.dumps([a.agent_name for a in agents]))
        )
        decision_id = cursor.lastrowid

        for agent in agents:
            self.conn.execute(
                "INSERT INTO agent_reports (decision_id, agent_name, symbol, direction, confidence, risk_score, analysis) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (decision_id, agent.agent_name, symbol, agent.direction, agent.confidence, agent.risk_score, agent.analysis[:1000])
            )
        self.conn.commit()
        return decision_id

    def update_outcome(self, decision_id: int, exit_price: float, pnl: float):
        self.conn.execute(
            "UPDATE decisions SET exit_price=?, pnl=?, pnl_pct=? WHERE id=?",
            (exit_price, pnl, (pnl/exit_price)*100 if exit_price else 0, decision_id)
        )
        self.conn.commit()

    def get_recent(self, symbol: str, limit: int = 5) -> list:
        cursor = self.conn.execute(
            "SELECT direction, confidence, pnl_pct FROM decisions WHERE symbol=? AND pnl IS NOT NULL ORDER BY id DESC LIMIT ?",
            (symbol, limit)
        )
        return cursor.fetchall()

    def get_win_rate(self, symbol: str = None) -> float:
        if symbol:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE symbol=? AND pnl IS NOT NULL", (symbol,))
            total = cursor.fetchone()[0]
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE symbol=? AND pnl > 0", (symbol,))
        else:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE pnl IS NOT NULL")
            total = cursor.fetchone()[0]
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE pnl > 0")
        wins = cursor.fetchone()[0]
        return wins / total if total > 0 else 0.5
