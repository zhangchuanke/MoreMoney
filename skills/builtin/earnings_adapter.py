"""
Skill: 财报季适配 (EarningsAdapter)

功能：
  - 财报季（1/4/7/10月）自动提升基本面权重
  - 对未公布财报的标的降低决策置信度
  - 对已公布利润大增/大降的标的给予信号方向修正建议
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from skills.base import SkillBase, SkillResult


class EarningsAdapterSkill(SkillBase):
    skill_id    = "earnings_adapter"
    name        = "财报季适配"
    description = "财报季自动提升基本面权重，对财报信号进行方向修正，降低无财报标的置信度"
    category    = "regime"
    priority    = 30

    FUND_BOOST      = +0.10
    TECH_PENALTY    = -0.05
    SENT_PENALTY    = -0.05

    def is_applicable(self, state: Dict) -> bool:
        return datetime.now().month in (1, 4, 7, 10)

    def run(self, state: Dict) -> SkillResult:
        month   = datetime.now().month
        signals: List[Dict] = state.get("signals", [])

        # 财报季基本面优先
        weight_adj: Dict[str, float] = {
            "fundamental": self.FUND_BOOST,
            "technical":   self.TECH_PENALTY,
            "sentiment":   self.SENT_PENALTY,
        }

        # 找出有基本面信号的标的
        fund_syms = {
            s.get("symbol")
            for s in signals
            if s.get("dimension") == "fundamental" and s.get("symbol")
        }
        all_syms = {
            s.get("symbol")
            for s in signals
            if s.get("symbol")
        }
        no_fund_syms = all_syms - fund_syms

        signal_adj: Dict = {}
        advice_parts: List[str] = [
            f"财报季 {month}月：基本面权重 +{self.FUND_BOOST:.0%}，"
            f"技术面/消息面各 {self.TECH_PENALTY:.0%}"
        ]

        # 无基本面信号的标的降低置信度（score轻微惩罚）
        for sym in no_fund_syms:
            signal_adj[sym] = {"score_delta": -0.05}

        if no_fund_syms:
            advice_parts.append(
                f"无基本面信号标的降权: {', '.join(sorted(no_fund_syms))}"
            )

        # 检测财报利空/利多信号，方向修正
        for sig in signals:
            if sig.get("dimension") != "fundamental":
                continue
            sym = sig.get("symbol", "")
            strength = sig.get("strength", 0)
            direction = sig.get("direction", "neutral")
            if strength >= 0.75:
                existing_delta = signal_adj.get(sym, {}).get("score_delta", 0)
                bonus = 0.08 if direction == "bullish" else -0.08
                signal_adj[sym] = {"score_delta": existing_delta + bonus}
                advice_parts.append(
                    f"{sym} 强基本面信号({direction})，财报季额外修正 {bonus:+.0%}"
                )

        return SkillResult(
            skill_id=self.skill_id,
            skill_name=self.name,
            triggered=True,
            advice=" | ".join(advice_parts),
            weight_adjustments=weight_adj,
            signal_adjustments=signal_adj,
            metadata={
                "month": month,
                "fund_covered_syms": len(fund_syms),
                "no_fund_syms": len(no_fund_syms),
            },
            confidence=0.82,
        )
