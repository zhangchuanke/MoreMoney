"""
SkillEngine — 技能执行引擎

在信号聚合阶段之前调用，将所有已启用 Skill 的结果
合并成统一的权重调整 + 信号调整 + 一票否决，
写入 state["skill_results"] 供 aggregator 消费。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from skills.registry import SkillRegistry
from skills.base import SkillResult

logger = logging.getLogger("skills.engine")


class SkillEngine:
    """单例技能引擎"""

    _instance: Optional["SkillEngine"] = None

    def __init__(self):
        self.registry = SkillRegistry.instance()

    @classmethod
    def instance(cls) -> "SkillEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def run_all(self, state: Dict) -> Dict:
        """
        执行所有已启用的 Skill，返回合并后的调整结果。

        Returns:
            {
              "skill_results":      List[SkillResult.as_dict()],
              "merged_weight_adj":  Dict[str, float],
              "merged_signal_adj":  Dict[str, Dict],
              "veto_active":        bool,
              "veto_reason":        str,
              "advice_lines":       List[str],
            }
        """
        results: List[SkillResult] = []
        for skill in self.registry.enabled_skills():
            r = skill.safe_run(state)
            if r is not None:
                results.append(r)
                logger.debug(
                    "[Engine] %s triggered=%s advice=%s",
                    skill.skill_id, r.triggered, r.advice[:60],
                )

        return self._merge(results)

    def run_one(self, skill_id: str, state: Dict) -> Optional[Dict]:
        """手动触发单个 Skill（供 API /api/skills/<id>/run 调用）"""
        skill = self.registry.get(skill_id)
        if not skill:
            return None
        r = skill.safe_run(state)
        return r.as_dict() if r else None

    # ------------------------------------------------------------------
    def _merge(self, results: List[SkillResult]) -> Dict:
        """将多个 SkillResult 合并为单一调整集合"""
        merged_weight: Dict[str, float] = {}
        merged_signal: Dict[str, Dict]  = {}
        veto        = False
        veto_reason = ""
        advice_lines: List[str] = []

        for r in results:
            if not r.triggered:
                continue

            # 权重累加
            for dim, delta in r.weight_adjustments.items():
                merged_weight[dim] = merged_weight.get(dim, 0.0) + delta

            # 信号调整：score_delta 累加，direction_override 最后写入的生效
            for sym, adj in r.signal_adjustments.items():
                if sym not in merged_signal:
                    merged_signal[sym] = {"score_delta": 0.0}
                merged_signal[sym]["score_delta"] = (
                    merged_signal[sym].get("score_delta", 0.0)
                    + adj.get("score_delta", 0.0)
                )
                if "direction_override" in adj:
                    merged_signal[sym]["direction_override"] = adj["direction_override"]

            # 一票否决：任一 Skill veto 则全局 veto
            if r.veto and not veto:
                veto        = True
                veto_reason = r.veto_reason

            if r.advice:
                advice_lines.append(f"[{r.skill_name}] {r.advice}")

        return {
            "skill_results":     [r.as_dict() for r in results],
            "merged_weight_adj": merged_weight,
            "merged_signal_adj": merged_signal,
            "veto_active":       veto,
            "veto_reason":       veto_reason,
            "advice_lines":      advice_lines,
        }
