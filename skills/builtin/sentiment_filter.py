"""
Skill: 情绪过滤 (SentimentFilter)

功能：
  - 市场情绪极度贪婪时，压制情绪面信号权重（避免追高）
  - 市场情绪极度恐惧时，提升基本面权重（价值发现）
  - 对低可信度情绪信号（confidence < 0.5）统一降权
"""
from __future__ import annotations

from typing import Dict, List

from skills.base import SkillBase, SkillResult


class SentimentFilterSkill(SkillBase):
    skill_id    = "sentiment_filter"
    name        = "情绪过滤"
    description = "极度贪婪时压制情绪面权重，极度恐惧时提升基本面权重，过滤低可信度情绪信号"
    category    = "signal"
    priority    = 25

    GREED_SENT_PENALTY    = -0.08   # 极度贪婪时情绪面权重削减
    FEAR_FUND_BOOST       = +0.08   # 极度恐惧时基本面权重提升
    LOW_CONF_THRESHOLD    = 0.50
    LOW_CONF_PENALTY      = -0.05

    def is_applicable(self, state: Dict) -> bool:
        sentiment = state.get("market_sentiment", "neutral")
        return sentiment in ("greed", "fear", "extreme_greed", "extreme_fear")

    def run(self, state: Dict) -> SkillResult:
        sentiment = state.get("market_sentiment", "neutral")
        signals: List[Dict] = state.get("signals", [])

        weight_adj: Dict[str, float] = {}
        signal_adj: Dict = {}
        advice_parts: List[str] = []

        if sentiment in ("greed", "extreme_greed"):
            weight_adj["sentiment"] = self.GREED_SENT_PENALTY
            advice_parts.append(
                f"市场情绪贪婪({sentiment})，压制情绪面权重 {self.GREED_SENT_PENALTY:.0%}"
            )
        elif sentiment in ("fear", "extreme_fear"):
            weight_adj["fundamental"] = self.FEAR_FUND_BOOST
            weight_adj["sentiment"]   = self.GREED_SENT_PENALTY  # 恐慌情绪同样不可信
            advice_parts.append(
                f"市场情绪恐惧({sentiment})，提升基本面防御权重 +{self.FEAR_FUND_BOOST:.0%}"
            )

        # 低可信度情绪信号降权
        low_conf_syms = set()
        for sig in signals:
            if (
                sig.get("dimension") == "sentiment"
                and sig.get("confidence", 1.0) < self.LOW_CONF_THRESHOLD
            ):
                sym = sig.get("symbol", "")
                if sym:
                    low_conf_syms.add(sym)
                    existing = signal_adj.get(sym, {}).get("score_delta", 0)
                    signal_adj[sym] = {"score_delta": existing + self.LOW_CONF_PENALTY}

        if low_conf_syms:
            advice_parts.append(
                f"低可信度情绪信号降权: {', '.join(sorted(low_conf_syms))}"
            )

        triggered = bool(weight_adj or signal_adj)
        return SkillResult(
            skill_id=self.skill_id,
            skill_name=self.name,
            triggered=triggered,
            advice=" | ".join(advice_parts) if advice_parts else "情绪正常，无需过滤",
            weight_adjustments=weight_adj,
            signal_adjustments=signal_adj,
            metadata={
                "sentiment": sentiment,
                "low_conf_filtered": len(low_conf_syms),
            },
            confidence=0.78,
        )
