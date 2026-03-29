"""
对手盘风险监控模块

针对主力资金、北向资金的异常流出，提供实时拦截逻辑，
避免系统在主力出货、外资撤离时仍持续买入高位标的。

监控维度：
  1. 北向资金单日净流出超阈值  -> 全市场暂停买入
  2. 个股北向资金净卖出超阈值  -> 该标的暂停买入
  3. 主力资金大单净流出异常    -> 该标的买入降级观望
  4. 北向资金连续 N 日净流出   -> 触发防御模式
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("risk.counterparty_monitor")


@dataclass
class CounterpartyConfig:
    # 北向资金单日净流出阈值（亿元，负值=流出）
    northbound_daily_outflow_threshold: float = -30.0
    # 个股北向单日净卖出阈值（万元）
    northbound_stock_outflow_threshold: float = -5000.0
    # 主力净流出阈值（万元）
    block_trade_outflow_threshold: float = -3000.0
    # 连续北向净流出天数触发防御模式
    northbound_consecutive_outflow_days: int = 3
    # 防御模式下是否完全禁止买入
    defense_mode_block_buy: bool = False


@dataclass
class CounterpartyRiskEvent:
    source: str
    symbol: str
    action_blocked: str
    severity: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __str__(self) -> str:
        return (
            f"[CounterpartyRisk][{self.severity.upper()}] "
            f"{self.symbol}({self.source}) {self.reason}"
        )


class CounterpartyMonitor:
    """
    对手盘风险监控器。

    用法::

        monitor = CounterpartyMonitor()
        monitor.update_northbound_market(net_buy_billion=-35.0)
        monitor.update_northbound_stock("sh600000", net_buy_wan=-6000)
        monitor.update_block_trade("sh600000", net_flow_wan=-4000)
        events = monitor.check(symbol="sh600000", action="buy")
        blocked = [e for e in events if e.severity == "block"]
    """

    def __init__(self, config: Optional[CounterpartyConfig] = None):
        self.config = config or CounterpartyConfig()
        self._northbound_market_flow: float = 0.0
        self._northbound_stock_flow: Dict[str, float] = {}
        self._block_trade_flow: Dict[str, float] = {}
        self._consecutive_outflow_days: int = 0
        self._defense_mode: bool = False

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------

    def update_northbound_market(self, net_buy_billion: float) -> None:
        """更新北向资金市场总净买入（亿元）。"""
        self._northbound_market_flow = net_buy_billion
        cfg = self.config
        if net_buy_billion < cfg.northbound_daily_outflow_threshold:
            self._consecutive_outflow_days += 1
            logger.warning(
                "[CounterpartyMonitor] 北向今日净流出 %.1f亿，连续 %d 天",
                net_buy_billion, self._consecutive_outflow_days,
            )
        else:
            self._consecutive_outflow_days = 0

        if self._consecutive_outflow_days >= cfg.northbound_consecutive_outflow_days:
            if not self._defense_mode:
                self._defense_mode = True
                logger.warning(
                    "[CounterpartyMonitor] 北向连续 %d 天净流出，进入防御模式",
                    self._consecutive_outflow_days,
                )
        else:
            self._defense_mode = False

    def update_northbound_stock(self, symbol: str, net_buy_wan: float) -> None:
        """更新个股北向净买入（万元）。"""
        self._northbound_stock_flow[symbol] = net_buy_wan

    def update_block_trade(self, symbol: str, net_flow_wan: float) -> None:
        """更新个股主力净流入（万元）。"""
        self._block_trade_flow[symbol] = net_flow_wan

    def reset_daily(self) -> None:
        """每日开盘前重置当日数据（保留连续流出天数计数）。"""
        self._northbound_market_flow = 0.0
        self._northbound_stock_flow.clear()
        self._block_trade_flow.clear()
        logger.info("[CounterpartyMonitor] 日间数据已重置")

    # ------------------------------------------------------------------
    # 检查接口
    # ------------------------------------------------------------------

    def check(
        self,
        symbol: str,
        action: str,
    ) -> List[CounterpartyRiskEvent]:
        """
        检查对手盘风险，返回事件列表。
        severity="block" 时调用方应拒绝该决策。
        """
        if action.lower() not in ("buy", "add"):
            return []

        cfg = self.config
        events: List[CounterpartyRiskEvent] = []

        # 1. 北向市场整体流出预警
        if self._northbound_market_flow < cfg.northbound_daily_outflow_threshold:
            severity = "block" if cfg.defense_mode_block_buy else "warn"
            events.append(CounterpartyRiskEvent(
                source="northbound_market",
                symbol="MARKET",
                action_blocked="buy",
                severity=severity,
                reason=(
                    f"北向今日净流出 {self._northbound_market_flow:.1f}亿 "
                    f"< 阈值 {cfg.northbound_daily_outflow_threshold:.1f}亿"
                ),
            ))

        # 2. 防御模式
        if self._defense_mode:
            severity = "block" if cfg.defense_mode_block_buy else "warn"
            events.append(CounterpartyRiskEvent(
                source="northbound_market",
                symbol="MARKET",
                action_blocked="buy",
                severity=severity,
                reason=(
                    f"北向连续 {self._consecutive_outflow_days} 天净流出，"
                    "系统处于防御模式"
                ),
            ))

        # 3. 个股北向流出
        stock_nb = self._northbound_stock_flow.get(symbol, 0.0)
        if stock_nb < cfg.northbound_stock_outflow_threshold:
            events.append(CounterpartyRiskEvent(
                source="northbound_stock",
                symbol=symbol,
                action_blocked="buy",
                severity="block",
                reason=(
                    f"个股北向今日净卖出 {stock_nb:.0f}万 "
                    f"< 阈值 {cfg.northbound_stock_outflow_threshold:.0f}万，"
                    "外资持续撤离，禁止买入"
                ),
            ))

        # 4. 主力大单净流出
        block_flow = self._block_trade_flow.get(symbol, 0.0)
        if block_flow < cfg.block_trade_outflow_threshold:
            events.append(CounterpartyRiskEvent(
                source="block_trade",
                symbol=symbol,
                action_blocked="buy",
                severity="warn",
                reason=(
                    f"主力今日净流出 {block_flow:.0f}万 "
                    f"< 阈值 {cfg.block_trade_outflow_threshold:.0f}万，"
                    "疑似主力出货，谨慎买入"
                ),
            ))

        for ev in events:
            if ev.severity == "block":
                logger.warning(str(ev))
            else:
                logger.info(str(ev))

        return events

    def is_defense_mode(self) -> bool:
        """当前是否处于防御模式。"""
        return self._defense_mode

    def status(self) -> Dict:
        """返回当前监控状态快照（供管控台展示）。"""
        return {
            "northbound_market_flow_billion": self._northbound_market_flow,
            "consecutive_outflow_days":       self._consecutive_outflow_days,
            "defense_mode":                   self._defense_mode,
            "northbound_stock_count":         len(self._northbound_stock_flow),
            "block_trade_count":              len(self._block_trade_flow),
        }


# ---------------------------------------------------------------------------
# 全局单例（跨节点共享）
# ---------------------------------------------------------------------------
_global_monitor = CounterpartyMonitor()


def get_counterparty_monitor() -> CounterpartyMonitor:
    """获取全局对手盘监控器单例。"""
    return _global_monitor
