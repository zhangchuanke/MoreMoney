"""
告警系统 - 异常行情、重要事件推送
"""
from datetime import datetime
from typing import List


class AlertSystem:
    """
    告警系统。
    当前实现：控制台打印 + 日志。
    可扩展：企业微信 / 钉钉 / Email / Telegram。
    """

    LEVELS = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}

    def __init__(self, min_level: str = "WARNING"):
        self.min_level = min_level
        self._history: List[dict] = []

    def send(
        self,
        title: str,
        body: str,
        level: str = "WARNING",
    ) -> None:
        if self.LEVELS.get(level, 0) < self.LEVELS.get(self.min_level, 0):
            return
        msg = {
            "level": level,
            "title": title,
            "body": body,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(msg)
        prefix = {"INFO": "[INFO]", "WARNING": "⚠ [WARN]", "CRITICAL": "🚨 [CRIT]"}[level]
        print(f"{prefix} {title}: {body}")

    def alert_circuit_breaker(self, reason: str) -> None:
        self.send("熔断触发", reason, level="CRITICAL")

    def alert_large_loss(self, pnl_pct: float) -> None:
        self.send(
            "日内大幅亏损",
            f"当日亏损 {pnl_pct:.2%}，已触及止损线",
            level="CRITICAL",
        )

    def alert_position_concentration(self, symbol: str, pct: float) -> None:
        self.send(
            "持仓集中度预警",
            f"{symbol} 仓位占比 {pct:.2%} 超过上限",
            level="WARNING",
        )

    def get_history(self, level: str = None) -> List[dict]:
        if level:
            return [m for m in self._history if m["level"] == level]
        return list(self._history)
