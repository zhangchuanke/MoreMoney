"""
Skill 注册中心

统一管理所有已注册的 Skill 实例，支持按 id/category 查询、启用/禁用。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from skills.base import SkillBase

logger = logging.getLogger("skills.registry")


class SkillRegistry:
    """单例技能注册中心"""

    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, SkillBase] = {}

    @classmethod
    def instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._auto_register()
        return cls._instance

    # ── 注册 ─────────────────────────────────────────────────────────
    def register(self, skill: SkillBase) -> None:
        if skill.skill_id in self._skills:
            logger.warning("[Registry] Skill '%s' 已存在，将覆盖", skill.skill_id)
        self._skills[skill.skill_id] = skill
        logger.info("[Registry] 注册 Skill: %s (%s)", skill.skill_id, skill.name)

    def _auto_register(self) -> None:
        """自动导入并注册所有内置 Skill"""
        from skills.builtin.trend_follower import TrendFollowerSkill
        from skills.builtin.risk_interceptor import RiskInterceptorSkill
        from skills.builtin.signal_booster import SignalBoosterSkill
        from skills.builtin.sentiment_filter import SentimentFilterSkill
        from skills.builtin.earnings_adapter import EarningsAdapterSkill

        for cls_ in (
            TrendFollowerSkill,
            RiskInterceptorSkill,
            SignalBoosterSkill,
            SentimentFilterSkill,
            EarningsAdapterSkill,
        ):
            self.register(cls_())

    # ── 查询 ─────────────────────────────────────────────────────────
    def get(self, skill_id: str) -> Optional[SkillBase]:
        return self._skills.get(skill_id)

    def all(self) -> List[SkillBase]:
        return sorted(self._skills.values(), key=lambda s: s.priority)

    def by_category(self, category: str) -> List[SkillBase]:
        return [
            s for s in self.all() if s.category == category
        ]

    def enabled_skills(self) -> List[SkillBase]:
        return [s for s in self.all() if s.enabled]

    # ── 控制 ─────────────────────────────────────────────────────────
    def enable(self, skill_id: str) -> bool:
        s = self._skills.get(skill_id)
        if s:
            s.enabled = True
            logger.info("[Registry] 启用 Skill: %s", skill_id)
            return True
        return False

    def disable(self, skill_id: str) -> bool:
        s = self._skills.get(skill_id)
        if s:
            s.enabled = False
            logger.info("[Registry] 禁用 Skill: %s", skill_id)
            return True
        return False

    # ── 序列化（供 API 返回） ─────────────────────────────────────────
    def to_list(self) -> List[Dict]:
        return [s.to_info() for s in self.all()]
