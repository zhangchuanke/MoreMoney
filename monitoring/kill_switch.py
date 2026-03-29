"""
Kill Switch —— 应急管控核心

提供线程安全的全局紧急控制状态，所有交易节点在执行前
必须调用 KillSwitch.is_trading_allowed() 检查。

控制状态：
  NORMAL      - 正常交易
  PAUSED      - 暂停交易（不开新仓，不减仓）
  EMERGENCY   - 紧急止损（强制清仓所有持仓）
  HALTED      - 完全停止（所有交易操作均拒绝）
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

logger = logging.getLogger("monitoring.kill_switch")


class TradingState(str, Enum):
    NORMAL    = "NORMAL"     # 正常交易
    PAUSED    = "PAUSED"     # 暂停交易
    EMERGENCY = "EMERGENCY"  # 紧急止损/清仓
    HALTED    = "HALTED"     # 完全停止


@dataclass
class KillSwitchEvent:
    state: str
    operator: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class KillSwitch:
    """
    全局 Kill Switch（线程安全单例）。

    用法::

        ks = KillSwitch.instance()

        # 执行节点调用
        if not ks.is_trading_allowed():
            return  # 拒绝交易

        if ks.is_emergency():
            # 强制清仓逻辑
            ...

        # 管控台调用
        ks.pause(operator="admin", reason="黑天鹅事件")
        ks.emergency_stop(operator="admin", reason="大盘熔断")
        ks.resume(operator="admin", reason="恢复正常")
    """

    _instance: Optional["KillSwitch"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = TradingState.NORMAL
        self._history: List[KillSwitchEvent] = []
        self._emergency_liquidate: bool = False  # 是否触发一键清仓

    @classmethod
    def instance(cls) -> "KillSwitch":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def is_trading_allowed(self) -> bool:
        """正常状态下返回 True，PAUSED/HALTED 返回 False。"""
        with self._lock:
            return self._state == TradingState.NORMAL

    def is_emergency(self) -> bool:
        """紧急止损/清仓模式。"""
        with self._lock:
            return self._state == TradingState.EMERGENCY

    def is_halted(self) -> bool:
        with self._lock:
            return self._state == TradingState.HALTED

    def should_liquidate(self) -> bool:
        """是否需要执行一键清仓。"""
        with self._lock:
            return self._emergency_liquidate

    def current_state(self) -> str:
        with self._lock:
            return self._state.value

    # ------------------------------------------------------------------
    # 控制操作
    # ------------------------------------------------------------------

    def pause(self, operator: str = "system", reason: str = "") -> None:
        """暂停交易（不开新仓，持仓不动）。"""
        self._transition(TradingState.PAUSED, operator, reason)

    def emergency_stop(
        self,
        operator: str = "system",
        reason: str = "",
        liquidate: bool = False,
    ) -> None:
        """紧急止损。liquidate=True 时触发一键清仓。"""
        with self._lock:
            self._state = TradingState.EMERGENCY
            self._emergency_liquidate = liquidate
            ev = KillSwitchEvent(
                state=TradingState.EMERGENCY.value,
                operator=operator,
                reason=reason + (" [一键清仓]" if liquidate else ""),
            )
            self._history.append(ev)
        logger.critical(
            "[KillSwitch] EMERGENCY_STOP | operator=%s | liquidate=%s | %s",
            operator, liquidate, reason,
        )

    def halt(
        self,
        operator: str = "system",
        reason: str = "",
        liquidate: bool = False,
    ) -> None:
        """完全停止所有交易操作。"""
        with self._lock:
            self._state = TradingState.HALTED
            self._emergency_liquidate = liquidate
            ev = KillSwitchEvent(
                state=TradingState.HALTED.value,
                operator=operator,
                reason=reason,
            )
            self._history.append(ev)
        logger.critical(
            "[KillSwitch] HALTED | operator=%s | %s", operator, reason
        )

    def resume(self, operator: str = "system", reason: str = "") -> None:
        """恢复正常交易。"""
        with self._lock:
            self._state = TradingState.NORMAL
            self._emergency_liquidate = False
            ev = KillSwitchEvent(
                state=TradingState.NORMAL.value,
                operator=operator,
                reason=reason,
            )
            self._history.append(ev)
        logger.info(
            "[KillSwitch] RESUMED | operator=%s | %s", operator, reason
        )

    def acknowledge_liquidation(self) -> None:
        """清仓完成后调用，清除清仓标志。"""
        with self._lock:
            self._emergency_liquidate = False

    # ------------------------------------------------------------------
    # 状态快照（供管控台使用）
    # ------------------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            last = self._history[-1] if self._history else None
            return {
                "state":              self._state.value,
                "emergency_liquidate": self._emergency_liquidate,
                "last_event": {
                    "operator":  last.operator,
                    "reason":    last.reason,
                    "timestamp": last.timestamp,
                } if last else {},
                "history_count": len(self._history),
            }

    def history(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "state":     e.state,
                    "operator":  e.operator,
                    "reason":    e.reason,
                    "timestamp": e.timestamp,
                }
                for e in self._history
            ]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _transition(self, new_state: TradingState, operator: str, reason: str) -> None:
        with self._lock:
            old = self._state
            self._state = new_state
            ev = KillSwitchEvent(
                state=new_state.value, operator=operator, reason=reason
            )
            self._history.append(ev)
        logger.warning(
            "[KillSwitch] %s -> %s | operator=%s | %s",
            old.value, new_state.value, operator, reason,
        )
