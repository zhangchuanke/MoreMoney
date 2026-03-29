"""
前置流动性风控模块

在市场扫描选股环节，直接剔除日均成交额低于阈值的标的，
规避小盘股止损无法成交的流动性风险。

集成方式：
  - 作为独立 LangGraph 节点插在 scanner -> market_regime 之间
  - 也可直接在 OrchestratorAgent.scan_market() 内调用
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("risk.liquidity_filter")


@dataclass
class LiquidityConfig:
    # 日均成交额下限（元）
    min_daily_amount: float = 50_000_000.0     # 默认 5000 万元
    # 流通市值下限（元）
    min_float_cap: float = 5e8                 # 5 亿市值
    # 换手率下限（%），0 表示不启用
    min_turnover_rate: float = 0.0
    # 是否开启市值过滤
    enable_float_cap_filter: bool = True
    # 是否开启换手率过滤
    enable_turnover_filter: bool = False


@dataclass
class LiquidityCheckResult:
    symbol: str
    passed: bool
    daily_amount: float            # 当日/近期成交额（元）
    float_cap: float               # 流通市值（元），0 表示未知
    turnover_rate: float           # 换手率（%），0 表示未知
    reject_reasons: List[str] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __str__(self) -> str:
        status = "PASS" if self.passed else f"REJECT({'; '.join(self.reject_reasons)})"
        return f"[{status}] {self.symbol} 日均成交额={self.daily_amount / 1e4:.0f}万"


class LiquidityFilter:
    """
    前置流动性过滤器。

    用法::

        flt = LiquidityFilter()
        passed, rejected = flt.filter(stock_list)

    stock_list 元素结构（与 RealtimeFeed.get_hot_stocks 返回格式一致）::

        {
            "symbol":        "sh600000",
            "amount":        当日成交额（元），
            "float_cap":     流通市值（元，可选），
            "turnover_rate": 换手率（%，可选），
        }
    """

    def __init__(self, config: Optional[LiquidityConfig] = None):
        self.config = config or LiquidityConfig()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def check(self, stock: Dict) -> LiquidityCheckResult:
        """检查单只标的流动性。"""
        cfg = self.config
        symbol        = stock.get("symbol", "")
        daily_amount  = float(stock.get("amount", 0))
        float_cap     = float(stock.get("float_cap", 0))
        turnover_rate = float(stock.get("turnover_rate", 0))

        reject_reasons: List[str] = []

        # 1. 成交额过滤（核心）
        if daily_amount < cfg.min_daily_amount:
            reject_reasons.append(
                f"日均成交额 {daily_amount / 1e4:.0f}万 < 阈值 {cfg.min_daily_amount / 1e4:.0f}万"
            )

        # 2. 流通市值过滤
        if cfg.enable_float_cap_filter and float_cap > 0:
            if float_cap < cfg.min_float_cap:
                reject_reasons.append(
                    f"流通市值 {float_cap / 1e8:.1f}亿 < 阈值 {cfg.min_float_cap / 1e8:.1f}亿"
                )

        # 3. 换手率过滤（可选）
        if cfg.enable_turnover_filter and cfg.min_turnover_rate > 0 and turnover_rate > 0:
            if turnover_rate < cfg.min_turnover_rate:
                reject_reasons.append(
                    f"换手率 {turnover_rate:.2f}% < 阈值 {cfg.min_turnover_rate:.2f}%"
                )

        passed = len(reject_reasons) == 0
        result = LiquidityCheckResult(
            symbol=symbol,
            passed=passed,
            daily_amount=daily_amount,
            float_cap=float_cap,
            turnover_rate=turnover_rate,
        reject_reasons=reject_reasons,
        )

        if not passed:
            logger.debug("[LiquidityFilter] 剔除 %s: %s", symbol, "; ".join(reject_reasons))

        return result

    def filter(
        self,
        stock_list: List[Dict],
    ) -> Tuple[List[Dict], List[LiquidityCheckResult]]:
        """
        批量过滤标的列表。

        Returns:
            passed_stocks: 通过流动性检查的标的列表（原始 dict）
            rejected_results: 被剔除的检查结果列表（供审计）
        """
        passed: List[Dict] = []
        rejected: List[LiquidityCheckResult] = []

        for stock in stock_list:
            result = self.check(stock)
            if result.passed:
                passed.append(stock)
            else:
                rejected.append(result)

        logger.info(
            "[LiquidityFilter] 流动性过滤完成: %d 只通过, %d 只剔除 "
            "(阈值=日均成交额%.0f万)",
            len(passed),
            len(rejected),
            self.config.min_daily_amount / 1e4,
        )
        return passed, rejected

    def filter_symbols(
        self,
        symbols: List[str],
        quote_map: Dict[str, Dict],
    ) -> Tuple[List[str], List[str]]:
        """
        按 symbol 列表过滤，quote_map 提供行情数据。

        Returns:
            passed_symbols: 通过过滤的 symbol 列表
            rejected_symbols: 被剔除的 symbol 列表
        """
        passed: List[str] = []
        rejected: List[str] = []

        for sym in symbols:
            quote = quote_map.get(sym, {})
            stock_data = {"symbol": sym, **quote}
            result = self.check(stock_data)
            if result.passed:
                passed.append(sym)
            else:
                rejected.append(sym)

        logger.info(
            "[LiquidityFilter] symbol 过滤: %d 通过, %d 剔除",
            len(passed), len(rejected),
        )
        return passed, rejected


# ---------------------------------------------------------------------------
# LangGraph 节点函数
# ---------------------------------------------------------------------------
async def liquidity_filter_node(state: dict) -> dict:
    """
    LangGraph 节点：前置流动性过滤。

    Reads:  state["target_symbols"], state["market_quotes"]
    Writes: state["target_symbols"] (过滤后), state["liquidity_rejected"], state["logs"]
    """
    from config.risk_params import RiskParams

    params = RiskParams()
    config = LiquidityConfig(
        min_daily_amount=params.LIQUIDITY_MIN_DAILY_AMOUNT,
        min_float_cap=params.LIQUIDITY_MIN_FLOAT_CAP,
        enable_float_cap_filter=True,
    )
    flt = LiquidityFilter(config)

    target_symbols: List[str] = state.get("target_symbols", [])
    market_quotes: Dict[str, Dict] = state.get("market_quotes", {})

    if not target_symbols:
        return {**state, "logs": ["[LiquidityFilter] 无待过滤标的，跳过"]}

    passed, rejected = flt.filter_symbols(target_symbols, market_quotes)

    rejected_info = [
        {"symbol": s, "reason": "流动性不足"} for s in rejected
    ]

    log_msg = (
        f"[LiquidityFilter] 前置流动性过滤: "
        f"{len(target_symbols)} -> {len(passed)} 只通过, "
        f"{len(rejected)} 只剔除"
    )
    logger.info(log_msg)

    return {
        **state,
        "target_symbols":     passed,
        "liquidity_rejected": rejected_info,
        "logs":               [log_msg],
    }
