"""
市场状态自适应的混合信号聚合器

替代 orchestrator.py 中原来基于 operator.add 的简单数值加减方式。

设计要点：
  基础层  - 多维度信号投票制（不依赖绝对数值，避免强度偏差导致的信号抵消）
  优先级层 - 一票否决 / 场景优先权重
            * 财报季   → 基本面（fundamental）优先
            * 题材炒作 → 消息面（sentiment）+ 资金流（capital_flow）优先
            * 极端行情 → 风控一票否决，聚合器直接返回 hold
            * 熊市     → 基本面防御优先
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from core.market_regime import MarketRegimeResult

logger = logging.getLogger("core.signal_aggregator")

# ---------------------------------------------------------------------------
# 权重边界（四维各维度上下限）
# 单维度权重不得超过 50%，不得低于 10%
# ---------------------------------------------------------------------------
WEIGHT_LOWER_BOUND: float = 0.10
WEIGHT_UPPER_BOUND: float = 0.50

DIMENSIONS = ("technical", "sentiment", "capital_flow", "fundamental")


@dataclass
class AggregatedSignal:
    symbol: str
    final_score: float          # -1.0 ~ +1.0，正值看多负值看空
    vote_result: str            # bullish / bearish / neutral
    vote_breakdown: Dict[str, str]   # 各维度投票方向
    vote_weights: Dict[str, float]   # 实际使用的权重
    veto_triggered: bool = False     # 是否触发一票否决
    veto_reason: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class AdaptiveSignalAggregator:
    """
    市场状态自适应信号聚合器。

    使用方式：
        aggregator = AdaptiveSignalAggregator()
        result = aggregator.aggregate(
            symbol="000001",
            signals=signal_list,       # List[MarketSignal]
            regime=regime_result,      # MarketRegimeResult
            is_earnings_season=False,
        )
    """

    def aggregate(
        self,
        symbol: str,
        signals: List[Dict],
        regime: MarketRegimeResult,
        is_earnings_season: bool = False,
    ) -> AggregatedSignal:
        """
        聚合某个标的的多维信号。

        Args:
            symbol:             股票代码
            signals:            该标的的 MarketSignal 列表
            regime:             当前市场风格识别结果
            is_earnings_season: 是否处于财报季（每年 1/4/7/10 月）

        Returns:
            AggregatedSignal
        """
        # ── 极端行情一票否决 ─────────────────────────────────────────────
        if regime.veto_active:
            logger.warning(
                "[Aggregator] %s 极端行情一票否决，强制输出 hold", symbol
            )
            return AggregatedSignal(
                symbol=symbol,
                final_score=0.0,
                vote_result="neutral",
                vote_breakdown={d: "neutral" for d in DIMENSIONS},
                vote_weights=regime.effective_weights(),
                veto_triggered=True,
                veto_reason=regime.description,
                confidence=0.0,
            )

        # ── 确定生效权重 ──────────────────────────────────────────────────
        weights = self._resolve_weights(
            base_weights=regime.effective_weights(),
            regime=regime.regime,
            is_earnings_season=is_earnings_season,
        )

        # ── 按维度分组信号 ────────────────────────────────────────────────
        dim_signals: Dict[str, List[Dict]] = {d: [] for d in DIMENSIONS}
        for sig in signals:
            if sig.get("symbol") == symbol:
                dim = sig.get("dimension", "")
                if dim in dim_signals:
                    dim_signals[dim].append(sig)

        # ── 各维度内部投票（majority vote） ──────────────────────────────
        vote_breakdown: Dict[str, str] = {}
        dim_scores:     Dict[str, float] = {}
        dim_confidences: Dict[str, float] = {}

        direction_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}

        for dim in DIMENSIONS:
            sigs = dim_signals[dim]
            if not sigs:
                vote_breakdown[dim] = "neutral"
                dim_scores[dim]     = 0.0
                dim_confidences[dim] = 0.0
                continue

            # 加权投票（strength * confidence 作为票权）
            vote_score = sum(
                direction_map.get(s.get("direction", "neutral"), 0.0)
                * s.get("strength", 0.5)
                * s.get("confidence", 0.5)
                for s in sigs
            )
            total_weight = sum(
                s.get("strength", 0.5) * s.get("confidence", 0.5)
                for s in sigs
            )
            normalized = vote_score / max(total_weight, 1e-6)

            if normalized > 0.2:
                vote_breakdown[dim] = "bullish"
            elif normalized < -0.2:
                vote_breakdown[dim] = "bearish"
            else:
                vote_breakdown[dim] = "neutral"

            dim_scores[dim] = normalized
            dim_confidences[dim] = min(1.0, total_weight / max(len(sigs), 1))

        # ── 场景优先级权重覆盖（一票优先，非否决） ────────────────────────
        # 财报季：若基本面投票为 bearish，直接下调总分（基本面一票降权）
        priority_veto_triggered = False
        priority_veto_reason = ""

        if is_earnings_season and vote_breakdown.get("fundamental") == "bearish":
            logger.info(
                "[Aggregator] %s 财报季基本面看空，触发场景优先降权", symbol
            )
            # 基本面权重提升到上限，其余维度等比缩减
            weights = self._boost_dimension(weights, "fundamental", target=WEIGHT_UPPER_BOUND)
            priority_veto_triggered = True
            priority_veto_reason = "财报季基本面看空优先"

        elif regime.regime == "theme" and vote_breakdown.get("sentiment") == "bullish":
            logger.info(
                "[Aggregator] %s 题材炒作期情绪看多，触发消息面优先", symbol
            )
            weights = self._boost_dimension(weights, "sentiment", target=WEIGHT_UPPER_BOUND)
            priority_veto_triggered = True
            priority_veto_reason = "题材炒作期消息面看多优先"

        # ── 计算综合评分 ──────────────────────────────────────────────────
        final_score = sum(
            dim_scores[d] * weights.get(d, 0.25) for d in DIMENSIONS
        )
        final_score = max(-1.0, min(1.0, final_score))  # 归一化到 [-1, 1]

        avg_conf = sum(dim_confidences[d] * weights.get(d, 0.25) for d in DIMENSIONS)

        if final_score > 0.15:
            vote_result = "bullish"
        elif final_score < -0.15:
            vote_result = "bearish"
        else:
            vote_result = "neutral"

        logger.debug(
            "[Aggregator] %s score=%.4f vote=%s regime=%s",
            symbol, final_score, vote_result, regime.regime,
        )

        return AggregatedSignal(
            symbol=symbol,
            final_score=round(final_score, 4),
            vote_result=vote_result,
            vote_breakdown=vote_breakdown,
            vote_weights=weights,
            veto_triggered=priority_veto_triggered,
            veto_reason=priority_veto_reason,
            confidence=round(avg_conf, 4),
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _resolve_weights(
        self,
        base_weights: Dict[str, float],
        regime: str,
        is_earnings_season: bool,
    ) -> Dict[str, float]:
        """
        对基准权重执行边界裁剪，确保每维度在 [LOWER, UPPER] 内，
        裁剪后重新归一化使总和为 1.0。
        """
        clipped: Dict[str, float] = {}
        for dim in DIMENSIONS:
            raw = base_weights.get(dim, 0.25)
            clipped[dim] = max(WEIGHT_LOWER_BOUND, min(WEIGHT_UPPER_BOUND, raw))

        total = sum(clipped.values())
        return {d: round(v / total, 6) for d, v in clipped.items()}

    def _boost_dimension(
        self,
        weights: Dict[str, float],
        target_dim: str,
        target: float,
    ) -> Dict[str, float]:
        """
        将 target_dim 的权重提升到 target（上限），
        其余维度等比缩减，并重新归一化。
        """
        current = weights.get(target_dim, 0.25)
        if current >= target:
            return weights  # 已经满足，不需要调整

        boost = target - current
        others = [d for d in DIMENSIONS if d != target_dim]
        other_total = sum(weights.get(d, 0.25) for d in others)

        new_weights = dict(weights)
        new_weights[target_dim] = target
        for d in others:
            ratio = weights.get(d, 0.25) / max(other_total, 1e-6)
            new_weights[d] = max(WEIGHT_LOWER_BOUND, weights.get(d, 0.25) - boost * ratio)

        # 归一化
        total = sum(new_weights.values())
        return {d: round(v / total, 6) for d, v in new_weights.items()}

    @staticmethod
    def is_earnings_season() -> bool:
        """判断当前是否为财报季（1/4/7/10 月）"""
        return datetime.now().month in (1, 4, 7, 10)
