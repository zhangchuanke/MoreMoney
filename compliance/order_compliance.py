"""
报撤单合规硬约束模块

拦截交易所异常交易监控红线，包括：
  1. 高频报撤单     —— 滑动窗口内报单+撤单总次数超限
  2. 虚假申报       —— 极短时间内撤销大比例申报（幌骗行为）
  3. 单笔申报占比超限 —— 单笔报单数量超过标的自由流通股本一定比例
  4. 单股单日报单次数超限 —— 避免同一标的反复刷单
  5. 撤单率超限     —— 当日撤单数 / 报单数超过阈值

所有检查均为同步、确定性规则，不走 LLM，确保实时性与强制性。
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 违规类型枚举
# ---------------------------------------------------------------------------
class ViolationType(str, Enum):
    HIGH_FREQ_ORDER_CANCEL   = "HIGH_FREQ_ORDER_CANCEL"    # 高频报撤单
    SPOOFING                 = "SPOOFING"                  # 虚假申报（幌骗）
    SINGLE_ORDER_RATIO       = "SINGLE_ORDER_RATIO"        # 单笔申报占比超限
    DAILY_ORDER_LIMIT        = "DAILY_ORDER_LIMIT"         # 单股单日报单次数超限
    CANCEL_RATE_EXCEEDED     = "CANCEL_RATE_EXCEEDED"      # 当日撤单率超限
    MARKET_MANIPULATION_RULE = "MARKET_MANIPULATION_RULE"  # LLM规则含市场操纵意图


@dataclass
class ComplianceViolation:
    violation_type: ViolationType
    symbol: str
    message: str
    severity: str           # "block" | "warn"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    extra: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"[{self.severity.upper()}][{self.violation_type}] "
            f"{self.symbol}: {self.message}"
        )


# ---------------------------------------------------------------------------
# 合规参数
# ---------------------------------------------------------------------------
@dataclass
class ComplianceParams:
    # 高频报撤单：hf_window_seconds 秒内，同一标的报单+撤单总次数不得超过 hf_max_orders
    hf_window_seconds: int        = 300      # 5 分钟滑动窗口
    hf_max_orders: int            = 20       # 窗口内最大报/撤单总次数

    # 虚假申报：spoof_window_seconds 内，撤单量/报单量 >= spoof_cancel_ratio
    #           且撤单数量 >= spoof_min_qty 股，视为幌骗
    spoof_window_seconds: int     = 60       # 1 分钟短窗口
    spoof_cancel_ratio: float     = 0.80     # 撤单比例阈值
    spoof_min_qty: int            = 1000     # 触发幌骗的最低撤单数量（股）
    spoof_min_orders_to_check: int = 3       # 短窗口内最少事件数才做比率检查

    # 单笔申报占比
    single_order_max_qty: int          = 1_000_000   # 绝对上限：100 万股
    single_order_float_ratio: float    = 0.01        # 流通股本占比上限 1%

    # 单股单日报单次数
    daily_order_limit_per_symbol: int  = 50

    # 当日撤单率上限
    daily_cancel_rate_limit: float     = 0.50        # 不超过 50%
    daily_cancel_rate_min_orders: int  = 3           # 至少有此数量报单才做比率检查


# ---------------------------------------------------------------------------
# 核心合规检查器
# ---------------------------------------------------------------------------
class OrderComplianceChecker:
    """
    线程安全的报撤单合规检查器。

    典型用法::

        checker = OrderComplianceChecker()

        # 下单前检查
        violations = checker.check_order(order)
        blocked = [v for v in violations if v.severity == "block"]
        if blocked:
            return  # 拒绝此订单

        # 成功报单后登记
        checker.record_order(order)

        # 撤单成功后登记
        checker.record_cancel(symbol, qty)
    """

    def __init__(self, params: Optional[ComplianceParams] = None):
        self.params = params or ComplianceParams()
        self._lock = threading.Lock()

        # symbol -> deque[(datetime, event_type, qty)]
        # event_type: "order" | "cancel"
        self._event_log: Dict[str, deque] = defaultdict(deque)

        # 当日统计（每自然日重置）
        self._daily_order_count: Dict[str, int]  = defaultdict(int)
        self._daily_cancel_count: Dict[str, int] = defaultdict(int)
        self._today: str = datetime.now().strftime("%Y-%m-%d")

        # 标的流通股本缓存（可由外部注入）
        self._float_shares: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def set_float_shares(self, symbol: str, shares: int) -> None:
        """注入标的流通股本（股数），用于单笔占比计算"""
        with self._lock:
            self._float_shares[symbol] = shares

    def check_order(self, order: Dict) -> List[ComplianceViolation]:
        """
        下单前合规检查。返回违规列表，调用方根据 severity 决定是否拦截。

        severity="block" → 强制拦截，禁止下单
        severity="warn"  → 仅记录警告，允许下单
        """
        with self._lock:
            self._rotate_daily_counters()
            violations: List[ComplianceViolation] = []
            symbol = order.get("symbol", "")
            qty    = order.get("quantity", 0)

            violations += self._check_single_order_ratio(symbol, qty)
            violations += self._check_daily_order_limit(symbol)
            violations += self._check_daily_cancel_rate(symbol)
            violations += self._check_high_freq(symbol)
            violations += self._check_spoofing(symbol)
            return violations

    def record_order(self, order: Dict) -> None:
        """成功报单后调用，记录本次报单事件"""
        with self._lock:
            self._rotate_daily_counters()
            symbol = order.get("symbol", "")
            qty    = order.get("quantity", 0)
            self._event_log[symbol].append((datetime.now(), "order", qty))
            self._daily_order_count[symbol] += 1

    def record_cancel(self, symbol: str, qty: int) -> None:
        """撤单成功后调用，记录本次撤单事件"""
        with self._lock:
            self._rotate_daily_counters()
            self._event_log[symbol].append((datetime.now(), "cancel", qty))
            self._daily_cancel_count[symbol] += 1

    def daily_summary(self) -> Dict:
        """返回当日报撤单统计摘要（供监控面板使用）"""
        with self._lock:
            result = {}
            all_symbols = set(
                list(self._daily_order_count) + list(self._daily_cancel_count)
            )
            for symbol in all_symbols:
                orders  = self._daily_order_count[symbol]
                cancels = self._daily_cancel_count[symbol]
                result[symbol] = {
                    "orders": orders,
                    "cancels": cancels,
                    "cancel_rate": round(cancels / max(orders, 1), 4),
                }
            return result

    # ------------------------------------------------------------------
    # 各项规则检查（均在持锁状态下调用）
    # ------------------------------------------------------------------

    def _check_single_order_ratio(self, symbol: str, qty: int) -> List[ComplianceViolation]:
        """单笔申报占比超限检查"""
        violations: List[ComplianceViolation] = []

        # 绝对数量上限
        if qty > self.params.single_order_max_qty:
            violations.append(ComplianceViolation(
                violation_type=ViolationType.SINGLE_ORDER_RATIO,
                symbol=symbol,
                message=(
                    f"单笔申报 {qty:,} 股超过绝对上限 "
                    f"{self.params.single_order_max_qty:,} 股"
                ),
                severity="block",
                extra={"qty": qty, "limit": self.params.single_order_max_qty},
            ))

        # 流通股本占比上限（若已注入流通股本）
        float_shares = self._float_shares.get(symbol, 0)
        if float_shares > 0:
            ratio = qty / float_shares
            if ratio > self.params.single_order_float_ratio:
                violations.append(ComplianceViolation(
                    violation_type=ViolationType.SINGLE_ORDER_RATIO,
                    symbol=symbol,
                    message=(
                        f"单笔申报 {qty:,} 股占流通股本 {ratio:.2%}，"
                        f"超过上限 {self.params.single_order_float_ratio:.2%}"
                    ),
                    severity="block",
                    extra={
                        "qty": qty,
                        "float_shares": float_shares,
                        "ratio": ratio,
                    },
                ))
        return violations

    def _check_daily_order_limit(self, symbol: str) -> List[ComplianceViolation]:
        """单股单日报单次数超限检查"""
        count = self._daily_order_count[symbol]
        if count >= self.params.daily_order_limit_per_symbol:
            return [ComplianceViolation(
                violation_type=ViolationType.DAILY_ORDER_LIMIT,
                symbol=symbol,
                message=(
                    f"今日 {symbol} 已报单 {count} 次，"
                    f"达到单日上限 {self.params.daily_order_limit_per_symbol} 次"
                ),
                severity="block",
                extra={
                    "count": count,
                    "limit": self.params.daily_order_limit_per_symbol,
                },
            )]
        return []

    def _check_daily_cancel_rate(self, symbol: str) -> List[ComplianceViolation]:
        """当日撤单率超限检查"""
        orders  = self._daily_order_count[symbol]
        cancels = self._daily_cancel_count[symbol]
        # 报单太少时不做比率检查，避免误报
        if orders < self.params.daily_cancel_rate_min_orders:
            return []
        rate = cancels / max(orders, 1)
        if rate > self.params.daily_cancel_rate_limit:
            return [ComplianceViolation(
                violation_type=ViolationType.CANCEL_RATE_EXCEEDED,
                symbol=symbol,
                message=(
                    f"今日 {symbol} 撤单率 {rate:.1%}（{cancels}/{orders}），"
                    f"超过上限 {self.params.daily_cancel_rate_limit:.1%}"
                ),
                severity="block",
                extra={
                    "cancel_rate": rate,
                    "orders": orders,
                    "cancels": cancels,
                },
            )]
        return []

    def _check_high_freq(self, symbol: str) -> List[ComplianceViolation]:
        """高频报撤单检查：滑动窗口内报单+撤单总次数超限"""
        cutoff = datetime.now() - timedelta(seconds=self.params.hf_window_seconds)
        self._trim_event_log(symbol, cutoff)
        count = len(self._event_log[symbol])
        if count >= self.params.hf_max_orders:
            return [ComplianceViolation(
                violation_type=ViolationType.HIGH_FREQ_ORDER_CANCEL,
                symbol=symbol,
                message=(
                    f"{self.params.hf_window_seconds}s 内 {symbol} 报/撤单 {count} 次，"
                    f"触及高频上限 {self.params.hf_max_orders} 次"
                ),
                severity="block",
                extra={
                    "window_count": count,
                    "window_seconds": self.params.hf_window_seconds,
                },
            )]
        return []

    def _check_spoofing(self, symbol: str) -> List[ComplianceViolation]:
        """虚假申报（幌骗）检查：短时间内大比例撤单"""
        cutoff = datetime.now() - timedelta(seconds=self.params.spoof_window_seconds)
        recent = [
            (ts, etype, qty)
            for ts, etype, qty in self._event_log[symbol]
            if ts >= cutoff
        ]
        if len(recent) < self.params.spoof_min_orders_to_check:
            return []

        order_qty  = sum(qty for _, etype, qty in recent if etype == "order")
        cancel_qty = sum(qty for _, etype, qty in recent if etype == "cancel")

        if order_qty == 0:
            return []

        ratio = cancel_qty / order_qty
        if (
            ratio >= self.params.spoof_cancel_ratio
            and cancel_qty >= self.params.spoof_min_qty
        ):
            return [ComplianceViolation(
                violation_type=ViolationType.SPOOFING,
                symbol=symbol,
                message=(
                    f"{self.params.spoof_window_seconds}s 内 {symbol} 撤单量 "
                    f"{cancel_qty:,} 股 / 报单量 {order_qty:,} 股 = {ratio:.1%}，"
                    f"疑似虚假申报（幌骗）"
                ),
                severity="block",
                extra={
                    "cancel_qty": cancel_qty,
                    "order_qty": order_qty,
                    "ratio": ratio,
                    "window_seconds": self.params.spoof_window_seconds,
                },
            )]
        return []

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _trim_event_log(self, symbol: str, cutoff: datetime) -> None:
        """清除 cutoff 之前的旧事件，保持 deque 紧凑"""
        log = self._event_log[symbol]
        while log and log[0][0] < cutoff:
            log.popleft()

    def _rotate_daily_counters(self) -> None:
        """日期变更时重置当日计数器"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._today:
            self._today = today
            self._daily_order_count.clear()
            self._daily_cancel_count.clear()
            self._event_log.clear()
