"""
知识库更新工具 - 将反思结论同步到各组件
"""
import json
from datetime import datetime
from typing import Dict, List

from core.memory.long_term import LongTermMemory


class KnowledgeUpdater:
    """
    将 ReflectionAgent 产生的新知识（规则、参数）持久化，
    并在下一轮运行时注入到对应 Agent。
    """

    def __init__(self):
        self.long_term = LongTermMemory()

    def apply_new_rules(self, rules: List[str]) -> None:
        """将新学习的规则写入长期记忆"""
        for rule in rules:
            self.long_term.save_rule(
                rule=rule,
                source="reflection",
                confidence=0.65,
            )
        if rules:
            print(f"[KnowledgeUpdater] 写入 {len(rules)} 条新规则")

    def apply_weight_update(self, new_weights: Dict[str, float]) -> None:
        """
        更新四维分析权重。
        写入配置文件，下次启动时生效。
        """
        try:
            with open("config/dimension_weights.json", "w", encoding="utf-8") as f:
                json.dump({
                    "weights": new_weights,
                    "updated_at": datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
            print(f"[KnowledgeUpdater] 四维权重已更新: {new_weights}")
        except Exception as e:
            print(f"[KnowledgeUpdater] 权重更新失败: {e}")

    def load_current_weights(self) -> Dict[str, float]:
        """加载当前权重（优先读文件，否则返回默认值）"""
        defaults = {
            "technical": 0.30,
            "sentiment": 0.25,
            "capital_flow": 0.25,
            "fundamental": 0.20,
        }
        try:
            with open("config/dimension_weights.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("weights", defaults)
        except FileNotFoundError:
            return defaults
