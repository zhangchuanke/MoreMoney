"""
Skill: 信号增强 (SignalBooster)

功能：
  - 对多维信号方向一致（共振）的标的给予评分加成
  - 单维度信号强度 >= 0.8 时额外加权
  - 对信号矛盾（多空分歧大）的标的施加惩罚
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from skills.base import SkillBase, SkillResult


class SignalBoosterSkill(SkillBase):
    skill_id    = "signal_booster"
    name        = "信号增强"
    description = "多维信号共振时加分，信号矛盾时降权，帮助聚合器更准确区分强弱标的"
    category    = "signal"
    priority    = 20

    RESONANCE_BONUS  = 0.12   # 三维以上共振的评分加成
    STRONG_BONUS     = 0.06   # 单信号强度>=0.8 的额外加成
    CONFLICT_PENALTY = -0.08  # 多空分歧时的惩罚

    def run(self, state: Dict) -> SkillResult:
        signals: List[Dict] = state.get("signals", [])
        if not signals:
            return SkillResult(
                skill_id=self.skill_id,
                skill_name=self.name,
                triggered=False,
                advice="无信号数据，信号增强技能未触发",
            )

        # 按标的分组
        sym_map: Dict[str, List[Dict]] = defaultdict(list)
        for sig in signals:
            sym = sig.get("symbol", "")
            if sym:
                sym_map[sym].append(sig)

        signal_adj: Dict = {}
        advice_parts: List[str] = []

        for sym, sigs in sym_map.items():
            directions = [s.get("direction", "neutral") for s in sigs]
            bull_cnt = directions.count("bullish")
            bear_cnt = directions.count("bearish")
            total    = len(directions)

            delta = 0.0

            # 共振判断：3 维以上方向一致
            if total >= 3:
                if bull_cnt >= 3:
                    delta += self.RESONANCE_BONUS
                    advice_parts.append(f"{sym} 多维看多共振(+{self.RESONANCE_BONUS:.0%})")
                elif bear_cnt >= 3:
                    delta -= self.RESONANCE_BONUS
                    advice_parts.append(f"{sym} 多维看空共振({self.RESONANCE_BONUS:.0%})")

            # 强信号加成
            strong = [s for s in sigs if s.get("strength", 0) >= 0.8]
            if strong:
                bonus = self.STRONG_BONUS * len(strong)
                # 强信号方向决定加减
                s_dir = strong[0].get("direction", "neutral")
                delta += bonus if s_dir == "bullish" else (-bonus if s_dir == "bearish" else 0)

            # 分歧惩罚：多空信号比例接近
            if total >= 2 and bull_cnt > 0 and bear_cnt > 0:
                conflict_ratio = min(bull_cnt, bear_cnt) / total
                if conflict_ratio >= 0.4:
                    delta += self.CONFLICT_PENALTY
                    advice_parts.append(f"{sym} 多空分歧惩罚({self.CONFLICT_PENALTY:.0%})")

            if delta != 0:
                signal_adj[sym] = {"score_delta": round(delta, 4)}

        return SkillResult(
            skill_id=self.skill_id,
            skill_name=self.name,
            triggered=bool(signal_adj),
            advice=" | ".join(advice_parts) if advice_parts else "信号无明显共振或分歧",
            signal_adjustments=signal_adj,
            metadata={"adjusted_symbols": len(signal_adj)},
            confidence=0.80,
        )
