"""
长期记忆 - 基于 SQLite + ChromaDB 1.x 的持久化记忆

chromadb v1.x 主要变化:
  - PersistentClient() 用法不变
  - Settings 从 chromadb.config 导入
  - anonymized_telemetry 通过 Settings 关闭
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings


class LongTermMemory:

    def __init__(
        self,
        db_path: str = "storage/database/memory.db",
        chroma_path: str = "storage/vector_store",
    ):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self._init_vector_store(chroma_path)

    # ------------------------------------------------------------------
    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    entry_price REAL,
                    exit_price  REAL,
                    quantity    INTEGER,
                    pnl         REAL,
                    pnl_pct     REAL,
                    hold_days   INTEGER,
                    signals     TEXT,
                    reasoning   TEXT,
                    outcome     TEXT,
                    market_date TEXT,
                    created_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    version     TEXT NOT NULL,
                    description TEXT,
                    params      TEXT,
                    performance TEXT,
                    created_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS learned_rules (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule           TEXT NOT NULL,
                    confidence     REAL    DEFAULT 0.5,
                    evidence_count INTEGER DEFAULT 1,
                    source         TEXT,
                    created_at     TEXT,
                    updated_at     TEXT
                );
            """)

    def _init_vector_store(self, chroma_path: str) -> None:
        Path(chroma_path).mkdir(parents=True, exist_ok=True)
        self._chroma = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._patterns = self._chroma.get_or_create_collection(
            name="trade_patterns",
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # 交易记录
    # ------------------------------------------------------------------
    def save_trade(self, record: Dict) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_records
                (symbol,action,entry_price,exit_price,quantity,pnl,pnl_pct,
                 hold_days,signals,reasoning,outcome,market_date,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.get("symbol"),      record.get("action"),
                    record.get("entry_price"), record.get("exit_price"),
                    record.get("quantity"),    record.get("pnl"),
                    record.get("pnl_pct"),     record.get("hold_days"),
                    json.dumps(record.get("signals", {}), ensure_ascii=False),
                    record.get("reasoning"),   record.get("outcome"),
                    record.get("market_date"), datetime.now().isoformat(),
                ),
            )
            trade_id = cursor.lastrowid
        self._index_pattern(trade_id, record)
        return trade_id

    def _index_pattern(self, trade_id: int, record: Dict) -> None:
        doc = (
            f"股票:{record.get('symbol')} "
            f"操作:{record.get('action')} "
            f"理由:{record.get('reasoning', '')} "
            f"结果:{record.get('outcome')}"
        )
        self._patterns.add(
            documents=[doc],
            ids=[f"trade_{trade_id}"],
            metadatas=[{
                "symbol":  record.get("symbol", ""),
                "outcome": record.get("outcome", ""),
                "pnl_pct": str(record.get("pnl_pct", 0)),
            }],
        )

    def search_similar_patterns(self, query: str, n_results: int = 5) -> List[Dict]:
        """语义检索相似历史交易模式"""
        results = self._patterns.query(query_texts=[query], n_results=n_results)
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(
                results["documents"][0],
                results["metadatas"][0],
            )
        ]

    def get_recent_trades(
        self, symbol: Optional[str] = None, last_n: int = 20
    ) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM trade_records WHERE symbol=? ORDER BY id DESC LIMIT ?",
                    (symbol, last_n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_records ORDER BY id DESC LIMIT ?",
                    (last_n,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 学习规则
    # ------------------------------------------------------------------
    def save_rule(
        self, rule: str, source: str = "reflection", confidence: float = 0.6
    ) -> None:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO learned_rules (rule,confidence,source,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (rule, confidence, source, now, now),
            )

    def get_rules(self, min_confidence: float = 0.5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM learned_rules WHERE confidence>=? ORDER BY confidence DESC",
                (min_confidence,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 策略版本
    # ------------------------------------------------------------------
    def save_strategy_version(
        self, version: str, description: str, params: Dict, performance: Dict
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO strategy_versions "
                "(version,description,params,performance,created_at) VALUES (?,?,?,?,?)",
                (
                    version,
                    description,
                    json.dumps(params, ensure_ascii=False),
                    json.dumps(performance, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
