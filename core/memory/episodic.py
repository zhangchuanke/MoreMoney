"""
事件记忆（Episodic Memory）- 存储关键市场事件与 Agent 的应对经验
用于：黑天鹅回顾、极端行情应对、板块轮动规律等
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class EpisodicMemory:
    """
    事件式记忆：记录 Agent 经历的关键市场事件及对应的处置结果。
    有别于长期记忆（逐笔交易），事件记忆聚焦「宏观场景」粒度。
    """

    def __init__(self, db_path: str = "storage/database/episodic.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,   -- crash / rally / black_swan / sector_rotation
                description TEXT,
                context     TEXT,            -- JSON：大盘状态、板块、宏观背景
                agent_response TEXT,         -- JSON：Agent 采取的操作
                outcome     TEXT,            -- JSON：结果评估
                lesson      TEXT,            -- 经验总结
                severity    REAL DEFAULT 0.5,-- 事件强度 0~1
                market_date TEXT,
                created_at  TEXT
            );
        """)
        conn.commit()
        conn.close()

    def record_episode(
        self,
        event_type: str,
        description: str,
        context: Dict,
        agent_response: Dict,
        outcome: Dict,
        lesson: str,
        severity: float = 0.5,
        market_date: Optional[str] = None,
    ) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO episodes
            (event_type,description,context,agent_response,outcome,lesson,severity,market_date,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                event_type,
                description,
                json.dumps(context, ensure_ascii=False),
                json.dumps(agent_response, ensure_ascii=False),
                json.dumps(outcome, ensure_ascii=False),
                lesson,
                severity,
                market_date or datetime.now().strftime("%Y-%m-%d"),
                datetime.now().isoformat(),
            ),
        )
        episode_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return episode_id

    def get_similar_episodes(
        self, event_type: str, min_severity: float = 0.3, last_n: int = 5
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM episodes
            WHERE event_type=? AND severity>=?
            ORDER BY id DESC LIMIT ?
            """,
            (event_type, min_severity, last_n),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_lessons(self) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT lesson FROM episodes WHERE lesson IS NOT NULL ORDER BY severity DESC"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
