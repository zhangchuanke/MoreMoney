"""
Skill 基类定义

所有 Skill 必须继承 SkillBase，实现 run() 方法。
SkillResult 是标准化的返回结构，供 SkillEngine 聚合后写入 state。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("skills.base")


@dataclass
class SkillResult:
    """技能执行结果"""
    skill_id: str
    skill_name: str
    triggered: bool                    # 是否实际触发了逻辑
    advice: str                        # human-readable 建议文本
    signal_adjustments: Dict[str, Any] = field(default_factory=dict)
    # 格式：{symbol: {"score_delta": 0.1, "direction_override": "bullish"}}
    weight_adjustments: Dict[str, float] = field(default_factory=dict)
    # 格式：{"technical": +0.05, "fundamental": -0.05}
    veto: bool = False                 # 一票否决（强制 hold）
    veto_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def as_dict(self) -> Dict:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "triggered": self.triggered,
            "advice": self.advice,
            "signal_adjustments": self.signal_adjustments,
            "weight_adjustments": self.weight_adjustments,
            "veto": self.veto,
            "veto_reason": self.veto_reason,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


class SkillBase(ABC):
    """
    所有交易 Skill 的抽象基类。

    子类需实现:
        run(state) -> SkillResult

    可选覆盖:
        is_applicable(state) -> bool   用于提前判断是否应该运行本技能
    """

    # ── 子类必须声明这些属性 ──────────────────────────────────────────
    skill_id: str = ""          # 唯一标识，snake_case
    name: str = ""              # 中文名称，用于 UI 展示
    description: str = ""       # 功能描述
    category: str = "general"   # market_analysis / risk_control / signal / regime
    priority: int = 50          # 执行优先级 0-100，数字越小越先执行
    # ─────────────────────────────────────────────────────────────────

    def __init__(self):
        self.enabled: bool = True
        self.execution_count: int = 0
        self.last_result: Optional[SkillResult] = None
        self.last_run_at: Optional[str] = None

    @abstractmethod
    def run(self, state: Dict) -> SkillResult:
        """
        执行 Skill 逻辑。

        Args:
            state: 当前 AgentState（只读，Skill 不应直接修改 state）

        Returns:
            SkillResult 标准化结果
        """
        ...

    def is_applicable(self, state: Dict) -> bool:
        """判断当前 state 是否适合运行本技能，默认总是适合"""
        return True

    def safe_run(self, state: Dict) -> Optional[SkillResult]:
        """带异常保护的执行入口（供 SkillEngine 调用）"""
        if not self.enabled:
            return None
        if not self.is_applicable(state):
            return None
        try:
            result = self.run(state)
            self.last_result = result
            self.last_run_at = datetime.now().isoformat()
            self.execution_count += 1
            return result
        except Exception as exc:
            logger.error(
                "[Skill:%s] 执行异常: %s", self.skill_id, exc, exc_info=True
            )
            return None

    def to_info(self) -> Dict:
        """供 API 返回的技能信息字典"""
        result_dict = self.last_result.as_dict() if self.last_result else None
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "enabled": self.enabled,
            "execution_count": self.execution_count,
            "last_run_at": self.last_run_at,
            "last_result": result_dict,
        }
