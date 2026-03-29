"""
个股极端波动熔断模块

补充个股级别的临时交易限制：
  1. 单日涨跌停限制  —— 当日已触及涨停/跌停板，禁止追高买入
  2. 单日振幅超阈值  —— 当日振幅超过设定值（如15%），暂停该标的新开仓
  3. 连续涨停计数    —— 连续涨停 N 板后禁止追入，避免追高
  4. 盘中快速拉升/砸盘 —— 短时间内涨/跌超阈值，触发临时冷静期

所有熔断规则均为确定性硬约束，不走 LLM。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("risk.stock_circuit_breaker")

# A 股涨跌停阈值（普通主板 10%，保守取 9.9%）
_LIMIT_UP_PCT   =  0.099
_LIMIT_DOWN_PCT = -0.099


@dataclass
class StockCircuitBreakerConfig:
    # 单日振幅熔断阈值（振幅 = (最高-最低)/昨收）
    max_daily_amplitude: float = 0.15
    # 连续涨停板数上限（超过则禁止追涨买入）
    max_consecutive_limit_up: int = 3
    # 盘中快速拉升检测时间窗口（分钟）
    intraday_rapid_window_minutes: int = 5
    # 5 分钟内涨跌超过此阈值触发冷静期
    intraday_rapid_threshold: float = 0.05
    # 冷静期时长（秒）
    cooldown_seconds: int = 1800
    # 跌停板是否仍允许持仓卖出（止损）
    allow_sell_on_limit_down: bool = True
    # 振幅过大时是否允许持仓减仓
    allow_reduce_on_amplitude: bool = True


@dataclass
class CircuitBreakerEvent:
    symbol: str
    reason: str
    action_blocked: str       # "buy" | "sell" | "all"
    severity: str = "block"   # "block" | "warn"
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    cooldown_until: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"[StockCB][{self.severity.upper()}] {self.symbol} "
            f"封锁={self.action_blocked} | {self.reason}"
        )


class StockCircuitBreaker:
    """
    个股极端波动熔断检查器（线程安全）。

    用法::

        cb = StockCircuitBreaker()
        events = cb.check(symbol, action="buy", quote=quote_dict)
        blocked = [e for e in events if e.severity == "block"]
        if blocked:
            pass  # 拒绝此买入决策

        # 每日行情更新后同步涨停计数
        cb.update_limit_up_count(symbol, is_limit_up=True)
    """

    def __init__(self, config: Optional[StockCircuitBreakerConfig] = None):
        self.config = config or StockCircuitBreakerConfig()
        self._lock = threading.Lock()
        # symbol -> cooldown 结束时间
        self._cooldown_map: Dict[str, datetime] = {}
        # symbol -> 连续涨停次数
        self._limit_up_count: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def check(
        self,
        symbol: str,
        action: str,
        quote: Dict,
    ) -> List[CircuitBreakerEvent]:
        """
        综合检查个股极端波动熔断。

        quote 期望字段（缺失则跳过对应检查）::

            {
                "price":         当前价,
                "last_close":    昨收价,
                "high":          当日最高,
                "low":           当日最低,
                "change_pct":    当日涨跌幅（小数，如 0.095 = 9.5%）,
                "price_5m_ago":  5 分钟前价格（可选）,
            }
        """
        cfg = self.config
        events: List[CircuitBreakerEvent] = []
        action_lower = action.lower()
        is_buy  = action_lower == "buy"
        is_sell = action_lower == "sell"

        change_pct = float(quote.get("change_pct", 0.0))
        last_close = float(quote.get("last_close", 0.0))
        high       = float(quote.get("high", 0.0))
        low        = float(quote.get("low", 0.0))
        price      = float(quote.get("price", 0.0))

        with self._lock:
            # 1. 冷静期检查（最高优先级，直接返回）
            cooldown_event = self._check_cooldown(symbol, action_lower)
            if cooldown_event:
                return [cooldown_event]

            # 2. 涨停板：禁止追涨买入
            if is_buy and change_pct >= _LIMIT_UP_PCT:
                events.append(CircuitBreakerEvent(
                    symbol=symbol,
                    reason=f"当日涨停 ({change_pct:.2%})，禁止追涨买入",
                    action_blocked="buy",
                    severity="block",
                ))

            # 3. 跌停板：若配置允许，持仓止损仍可卖出
            if change_pct <= _LIMIT_DOWN_PCT:
                if is_buy:
                    events.append(CircuitBreakerEvent(
                        symbol=symbol,
                        reason=f"当日跌停 ({change_pct:.2%})，禁止买入",
                        action_blocked="buy",
                        severity="block",
                    ))
                elif is_sell and not cfg.allow_sell_on_limit_down:
                    events.append(CircuitBreakerEvent(
                        symbol=symbol,
                        reason=f"当日跌停 ({change_pct:.2%})，卖出可能无法成交",
                        action_blocked="sell",
                        severity="warn",
                    ))

            # 4. 单日振幅超阈值：禁止新开仓
            if last_close > 0 and high > 0 and low > 0:
                amplitude = (high - low) / last_close
                if amplitude >= cfg.max_daily_amplitude:
                    if is_buy:
                        events.append(CircuitBreakerEvent(
                            symbol=symbol,
                            reason=(
                                f"单日振幅 {amplitude:.2%} 超过阈值 "
                                f"{cfg.max_daily_amplitude:.2%}，暂停新开仓"
                            ),
                            action_blocked="buy",
                            severity="block",
                        ))
                    elif is_sell and not cfg.allow_reduce_on_amplitude:
                        events.append(CircuitBreakerEvent(
                            symbol=symbol,
                            reason=f"单日振幅 {amplitude:.2%} 过大，卖出须谨慎",
                            action_blocked="sell",
                            severity="warn",
                        ))

            # 5. 连续涨停板超限：禁止追涨
            if is_buy:
                limit_count = self._limit_up_count.get(symbol, 0)
                if limit_count >= cfg.max_consecutive_limit_up:
                    events.append(CircuitBreakerEvent(
                        symbol=symbol,
                        reason=(
                            f"已连续涨停 {limit_count} 板（上限 "
                            f"{cfg.max_consecutive_limit_up} 板），禁止追高"
                        ),
                        action_blocked="buy",
                        severity="block",
                    ))

            # 6. 盘中快速拉升/砸盘检测
            price_5m_ago = float(quote.get("price_5m_ago", 0.0))
            if price > 0 and price_5m_ago > 0:
                rapid_chg = (price - price_5m_ago) / price_5m_ago
                if abs(rapid_chg) >= cfg.intraday_rapid_threshold:
                    cooldown_until = datetime.now() + timedelta(
                        seconds=cfg.cooldown_seconds
                    )
                    self._cooldown_map[symbol] = cooldown_until
                    direction = "拉升" if rapid_chg > 0 else "砸盘"
                    events.append(CircuitBreakerEvent(
                        symbol=symbol,
                        reason=(
                            f"{cfg.intraday_rapid_window_minutes}分钟内盘中{direction} "
                            f"{rapid_chg:.2%}，触发冷静期 "
                            f"{cfg.cooldown_seconds // 60} 分钟"
                        ),
                        action_blocked="all",
                        severity="block",
                        cooldown_until=cooldown_until.isoformat(),
                    ))

        # 记录日志
        for ev in events:
            if ev.severity == "block":
                logger.warning(str(ev))
            else:
                logger.info(str(ev))

        return events

    def update_limit_up_count(self, symbol: str, is_limit_up: bool) -> None:
        """
        更新个股连续涨停计数。
        每日收盘后由 RiskAgent 调用。

        - is_limit_up=True:  计数 +1
        - is_limit_up=False: 重置为 0（连续涨停中断）
        """
        with self._lock:
            if is_limit_up:
                self._limit_up_count[symbol] = self._limit_up_count.get(symbol, 0) + 1
                logger.info(
                    "[StockCB] %s 连续涨停 %d 板",
                    symbol, self._limit_up_count[symbol],
                )
            else:
                if symbol in self._limit_up_count:
                    self._limit_up_count.pop(symbol)

    def clear_cooldown(self, symbol: str) -> None:
        """手动解除个股冷静期（Kill Switch 操作时使用）"""
        with self._lock:
            self._cooldown_map.pop(symbol, None)

    def status(self) -> Dict:
        """返回当前熔断状态快照（供管控台展示）"""
        with self._lock:
            now = datetime.now()
            return {
                "cooldown_active": {
                    sym: until.isoformat()
                    for sym, until in self._cooldown_map.items()
                    if until > now
                },
                "limit_up_counts": dict(self._limit_up_count),
            }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _check_cooldown(
        self, symbol: str, action: str
    ) -> Optional[CircuitBreakerEvent]:
        """检查标的是否在冷静期内，在锁内调用。"""
        until = self._cooldown_map.get(symbol)
        if until and datetime.now() < until:
            return CircuitBreakerEvent(
                symbol=symbol,
                reason=f"冷静期内，到期 {until.strftime('%H:%M:%S')}",
                action_blocked="all",
                severity="block",
                cooldown_until=until.isoformat(),
            )
        # 冷静期已过，清除
        if until:
            self._cooldown_map.pop(symbol, None)
        return None


# ---------------------------------------------------------------------------
# LangGraph 节点函数（在 risk 节点内部调用，非独立节点）
# ---------------------------------------------------------------------------
_global_cb = StockCircuitBreaker()


def get_stock_circuit_breaker() -> StockCircuitBreaker:
    """获取全局单例熔断器（跨节点共享状态）。"""
    return _global_cb
