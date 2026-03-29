"""
回测验证前置关卡

LLM 生成的新权重 / 新规则，在写入配置生效之前，必须先通过此模块：
  1. 拉取至少 1 年历史价格数据（优先覆盖 1 个完整市场风格周期）
  2. 使用候选权重构建信号函数，驱动 BacktestEngine 运行回测
  3. 核心指标校验：夏普比率、最大回撤、胜率必须同时达标
  4. 对比基准（当前权重回测结果），候选权重不得显著劣化
  5. 全部通过后返回 PASS，否则返回 FAIL + 原因，禁止写入

用法：
    gate = BacktestGate()
    result = gate.validate(candidate_weights, price_data, baseline_weights)
    if result.passed:
        knowledge_updater.apply_weight_update(candidate_weights)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from tools.technical.backtest_engine import BacktestEngine

logger = logging.getLogger("self_evolution.backtest_gate")

# ---------------------------------------------------------------------------
# 回测达标阈值
# ---------------------------------------------------------------------------
MIN_SHARPE_RATIO: float   = 0.5    # 夏普比率下限
MAX_DRAWDOWN_LIMIT: float = -0.20  # 最大回撤上限（负值，-20%）
MIN_WIN_RATE: float       = 0.40   # 最低胜率
MIN_TRADE_COUNT: int      = 30     # 最少成交笔数（避免样本过少误判）

# 候选权重 vs 基准权重对比容差
SHARPE_DEGRADATION_LIMIT: float   = -0.20  # 夏普下降不超过 0.20
DRAWDOWN_DEGRADATION_LIMIT: float =  0.05  # 最大回撤不得比基准恶化超过 5 个百分点


@dataclass
class BacktestGateResult:
    passed: bool
    candidate_metrics: Dict           # 候选权重回测指标
    baseline_metrics: Dict            # 基准权重回测指标
    failure_reasons: List[str] = field(default_factory=list)
    notes: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        if self.passed:
            return (
                f"[BacktestGate] {status} | "
                f"Sharpe={self.candidate_metrics.get('sharpe', 'N/A')}, "
                f"MaxDD={self.candidate_metrics.get('max_drawdown', 'N/A')}, "
                f"WinRate={self.candidate_metrics.get('win_rate', 'N/A')}"
            )
        return f"[BacktestGate] {status} | 原因: {'; '.join(self.failure_reasons)}"


class BacktestGate:
    """
    回测验证前置关卡。

    price_data 格式与 BacktestEngine.run() 相同：
        Dict[symbol, pd.DataFrame(OHLCV, DatetimeIndex)]

    signal_fn_builder 是可调用工厂：
        (weights: Dict[str, float]) -> Callable[[symbol, df_slice], str]

    若调用方未提供 signal_fn_builder，则使用内置的基于权重的简单动量信号函数，
    用于快速验证权重方向是否合理（不代替完整策略回测）。
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
    ):
        self.engine = BacktestEngine(
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
        )

    def validate(
        self,
        candidate_weights: Dict[str, float],
        price_data: Dict,
        baseline_weights: Optional[Dict[str, float]] = None,
        signal_fn_builder: Optional[Callable] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BacktestGateResult:
        """
        执行回测验证。

        Args:
            candidate_weights:  LLM 建议的候选权重
            price_data:         历史价格数据，至少覆盖 1 年
            baseline_weights:   当前生效的基准权重（为 None 时跳过对比检验）
            signal_fn_builder:  (weights) -> signal_fn 工厂，为 None 时用内置函数
            start_date:         回测起始日期 YYYY-MM-DD
            end_date:           回测结束日期 YYYY-MM-DD

        Returns:
            BacktestGateResult
        """
        if not price_data:
            reason = "price_data 为空，无法执行回测验证"
            logger.error("[BacktestGate] %s", reason)
            return BacktestGateResult(
                passed=False,
                candidate_metrics={},
                baseline_metrics={},
                failure_reasons=[reason],
            )

        builder = signal_fn_builder or self._default_signal_fn_builder

        # ── 1. 候选权重回测 ──────────────────────────────────────────────
        candidate_fn = builder(candidate_weights)
        candidate_metrics = self.engine.run(
            price_data=price_data,
            signal_fn=candidate_fn,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("[BacktestGate] 候选权重回测完成: %s", candidate_metrics)

        # ── 2. 基准权重回测（用于对比） ───────────────────────────────────
        baseline_metrics: Dict = {}
        if baseline_weights:
            baseline_fn = builder(baseline_weights)
            baseline_metrics = self.engine.run(
                price_data=price_data,
                signal_fn=baseline_fn,
                start_date=start_date,
                end_date=end_date,
            )
            logger.info("[BacktestGate] 基准权重回测完成: %s", baseline_metrics)

        # ── 3. 绝对阈值校验 ──────────────────────────────────────────────
        failure_reasons: List[str] = []

        sharpe = candidate_metrics.get("sharpe", 0.0)
        max_dd = candidate_metrics.get("max_drawdown", -1.0)
        win_rate = candidate_metrics.get("win_rate", 0.0)
        trade_count = candidate_metrics.get("trade_count", 0)

        if trade_count < MIN_TRADE_COUNT:
            failure_reasons.append(
                f"成交笔数不足（{trade_count} < {MIN_TRADE_COUNT}），样本过少，结果不可信"
            )

        if sharpe < MIN_SHARPE_RATIO:
            failure_reasons.append(
                f"夏普比率不达标（{sharpe:.3f} < {MIN_SHARPE_RATIO}）"
            )

        if max_dd < MAX_DRAWDOWN_LIMIT:
            failure_reasons.append(
                f"最大回撤超限（{max_dd:.2%} < {MAX_DRAWDOWN_LIMIT:.2%}）"
            )

        if win_rate < MIN_WIN_RATE:
            failure_reasons.append(
                f"胜率不达标（{win_rate:.2%} < {MIN_WIN_RATE:.2%}）"
            )

        # ── 4. 对比基准校验 ───────────────────────────────────────────────
        if baseline_metrics:
            base_sharpe = baseline_metrics.get("sharpe", 0.0)
            base_dd = baseline_metrics.get("max_drawdown", 0.0)

            sharpe_delta = sharpe - base_sharpe
            if sharpe_delta < SHARPE_DEGRADATION_LIMIT:
                failure_reasons.append(
                    f"夏普比率相对基准退化过大（Δ={sharpe_delta:.3f} < {SHARPE_DEGRADATION_LIMIT}）"
                )

            dd_delta = max_dd - base_dd  # 两者均为负值，delta 越小越差
            if dd_delta < -DRAWDOWN_DEGRADATION_LIMIT:
                failure_reasons.append(
                    f"最大回撤相对基准恶化过大（Δ={dd_delta:.2%}）"
                )

        passed = len(failure_reasons) == 0

        result = BacktestGateResult(
            passed=passed,
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            failure_reasons=failure_reasons,
            notes=(
                f"数据覆盖: {start_date or '最早'} ~ {end_date or '最新'}, "
                f"成交 {trade_count} 笔"
            ),
        )

        if passed:
            logger.info("[BacktestGate] 回测验证通过: %s", result)
        else:
            logger.warning("[BacktestGate] 回测验证未通过: %s", result)

        return result

    # ------------------------------------------------------------------
    # 内置默认信号函数工厂（基于技术指标动量，快速近似验证）
    # ------------------------------------------------------------------
    @staticmethod
    def _default_signal_fn_builder(weights: Dict[str, float]) -> Callable:
        """
        用权重中 technical 维度的强度作为简单动量信号（MA5 vs MA20 金叉死叉）。
        weights 参数保留供扩展：未来可根据权重调整各维度信号融合比例。
        """
        tech_weight = weights.get("technical", 0.30)

        def signal_fn(symbol: str, df_slice) -> str:  # noqa: ANN001
            if len(df_slice) < 20:
                return "hold"
            try:
                close = df_slice["close"]
                ma5  = close.iloc[-5:].mean()
                ma20 = close.iloc[-20:].mean()
                # 权重越高，趋势跟随越灵敏（通过阈值缩放体现）
                threshold = 0.005 * (1 - tech_weight)  # 权重高 → 阈值低 → 更容易触发
                if ma5 > ma20 * (1 + threshold):
                    return "buy"
                if ma5 < ma20 * (1 - threshold):
                    return "sell"
                return "hold"
            except Exception:
                return "hold"

        return signal_fn
