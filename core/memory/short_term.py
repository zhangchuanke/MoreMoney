"""
短期记忆（当日内）- 存储当日分析结果、信号、决策
使用内存字典，盘后清空
"""
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import deque


class ShortTermMemory:
    """
    当日短期记忆，存储:
    - 最近N条信号
    - 最近N条决策
    - 当日新闻摘要
    - 板块热度快照
    """

    def __init__(self, max_signals: int = 200, max_decisions: int = 50):
        self._signals: deque = deque(maxlen=max_signals)
        self._decisions: deque = deque(maxlen=max_decisions)
        self._news_cache: Dict[str, List[Dict]] = {}   # symbol -> news list
        self._sector_snapshot: Dict[str, float] = {}   # sector -> heat score
        self._price_cache: Dict[str, Dict] = {}         # symbol -> latest price info
        self._created_at: str = datetime.now().isoformat()

    # ---------- 信号 ----------
    def add_signal(self, signal: Dict) -> None:
        signal["stored_at"] = datetime.now().isoformat()
        self._signals.append(signal)

    def get_signals(
        self,
        symbol: Optional[str] = None,
        dimension: Optional[str] = None,
        last_n: int = 10
    ) -> List[Dict]:
        signals = list(self._signals)
        if symbol:
            signals = [s for s in signals if s.get("symbol") == symbol]
        if dimension:
            signals = [s for s in signals if s.get("dimension") == dimension]
        return signals[-last_n:]

    # ---------- 决策 ----------
    def add_decision(self, decision: Dict) -> None:
        decision["stored_at"] = datetime.now().isoformat()
        self._decisions.append(decision)

    def get_recent_decisions(self, symbol: Optional[str] = None, last_n: int = 5) -> List[Dict]:
        decisions = list(self._decisions)
        if symbol:
            decisions = [d for d in decisions if d.get("symbol") == symbol]
        return decisions[-last_n:]

    # ---------- 新闻 ----------
    def cache_news(self, symbol: str, news_list: List[Dict]) -> None:
        self._news_cache[symbol] = news_list

    def get_news(self, symbol: str) -> List[Dict]:
        return self._news_cache.get(symbol, [])

    # ---------- 价格快照 ----------
    def update_price(self, symbol: str, price_info: Dict) -> None:
        price_info["updated_at"] = datetime.now().isoformat()
        self._price_cache[symbol] = price_info

    def get_price(self, symbol: str) -> Optional[Dict]:
        return self._price_cache.get(symbol)

    # ---------- 板块 ----------
    def update_sector(self, sector: str, heat: float) -> None:
        self._sector_snapshot[sector] = heat

    def get_hot_sectors(self, top_n: int = 5) -> List[tuple]:
        sorted_sectors = sorted(self._sector_snapshot.items(), key=lambda x: x[1], reverse=True)
        return sorted_sectors[:top_n]

    # ---------- 清空（盘后调用）----------
    def clear(self) -> None:
        self._signals.clear()
        self._decisions.clear()
        self._news_cache.clear()
        self._sector_snapshot.clear()
        self._price_cache.clear()
        self._created_at = datetime.now().isoformat()
        print("[ShortTermMemory] 当日记忆已清空")
